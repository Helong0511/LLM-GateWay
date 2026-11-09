"""Prometheus 文本格式指标。

刻意不引入 `prometheus_client`：本项目只需要计数器、直方图和即时 gauge 三种原语，
自建注册表可以避免多一个运行期依赖，也免去锁文件同步成本。

渲染遵循 Prometheus text exposition format 0.0.4，`/metrics` 可被直接抓取。
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

# 标签顺序固定，避免同一指标因标签顺序不同产生两条时间序列
LabelKey = tuple[tuple[str, str], ...]


def _key(labels: Mapping[str, str] | None) -> LabelKey:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_labels(names: Iterable[str], key: LabelKey) -> str:
    pairs = dict(key)
    if not names:
        return ""
    rendered = ",".join(f'{name}="{_escape(pairs.get(name, ""))}"' for name in names)
    return "{" + rendered + "}"


@dataclass
class _Histogram:
    buckets: tuple[float, ...]
    counts: list[int] = field(default_factory=list)
    total: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if not self.counts:
            self.counts = [0] * len(self.buckets)


class MetricsRegistry:
    """进程内指标注册表。多 worker 时由 Prometheus 侧按实例聚合（sum / histogram_quantile）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._meta: dict[str, tuple[str, str]] = {}
        self._label_names: dict[str, tuple[str, ...]] = {}
        self._counters: dict[tuple[str, LabelKey], float] = defaultdict(float)
        self._histograms: dict[tuple[str, LabelKey], _Histogram] = {}
        self._gauges: dict[tuple[str, LabelKey], float] = {}

    def declare(self, name: str, kind: str, help_text: str, labels: Iterable[str] = ()) -> None:
        self._meta[name] = (kind, help_text)
        self._label_names[name] = tuple(labels)

    def counter(self, name: str, labels: Mapping[str, str] | None = None, amount: float = 1.0) -> None:
        with self._lock:
            self._counters[(name, _key(labels))] += float(amount)

    def observe(
        self, name: str, value: float, labels: Mapping[str, str] | None = None
    ) -> None:
        key = (name, _key(labels))
        with self._lock:
            bucket = self._histograms.get(key)
            if bucket is None:
                bucket = _Histogram(self._histogram_buckets(name))
                self._histograms[key] = bucket
            for index, bound in enumerate(bucket.buckets):
                if value <= bound:
                    bucket.counts[index] += 1
                    break
            else:
                # 超出最大桶的值只进 +Inf 与 _sum/_count
                pass
            bucket.total += value
            bucket.count += 1

    def gauge(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        with self._lock:
            self._gauges[(name, _key(labels))] = float(value)

    def add_gauge(
        self, name: str, amount: float = 1.0, labels: Mapping[str, str] | None = None
    ) -> None:
        """用于 in-flight 这类需要加减的 gauge。"""
        with self._lock:
            key = (name, _key(labels))
            self._gauges[key] = self._gauges.get(key, 0.0) + float(amount)

    def _histogram_buckets(self, name: str) -> tuple[float, ...]:
        return HISTOGRAM_BUCKETS.get(name, (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0))

    def render(self) -> str:
        with self._lock:
            counters = dict(self._counters)
            histograms = {
                key: _Histogram(
                    bucket.buckets, list(bucket.counts), bucket.total, bucket.count
                )
                for key, bucket in self._histograms.items()
            }
            gauges = dict(self._gauges)
            meta = dict(self._meta)
            label_names = dict(self._label_names)

        lines: list[str] = []
        for name in sorted(meta):
            kind, help_text = meta[name]
            names = label_names.get(name, ())
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")
            if kind == "counter":
                for (metric, key), value in sorted(counters.items()):
                    if metric != name:
                        continue
                    lines.append(f"{name}{_format_labels(names, key)} {_number(value)}")
            elif kind == "gauge":
                for (metric, key), value in sorted(gauges.items()):
                    if metric != name:
                        continue
                    lines.append(f"{name}{_format_labels(names, key)} {_number(value)}")
            elif kind == "histogram":
                for (metric, key), bucket in sorted(histograms.items()):
                    if metric != name:
                        continue
                    cumulative = 0
                    for bound, count in zip(bucket.buckets, bucket.counts, strict=False):
                        cumulative += count
                        labels = _format_labels((*names, "le"), (*key, ("le", _number(bound))))
                        lines.append(f"{name}_bucket{labels} {cumulative}")
                    labels = _format_labels((*names, "le"), (*key, ("le", "+Inf")))
                    lines.append(f"{name}_bucket{labels} {bucket.count}")
                    base = _format_labels(names, key)
                    lines.append(f"{name}_sum{base} {_number(bucket.total)}")
                    lines.append(f"{name}_count{base} {bucket.count}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """仅供测试使用。"""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._gauges.clear()


def _number(value: float) -> str:
    if value == float("inf"):
        return "+Inf"
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


HISTOGRAM_BUCKETS: dict[str, tuple[float, ...]] = {}

REGISTRY = MetricsRegistry()

HTTP_REQUESTS = "forge_http_requests_total"
HTTP_DURATION = "forge_http_request_duration_seconds"
HTTP_INFLIGHT = "forge_http_inflight_requests"
API_ERRORS = "forge_api_errors_total"
HOLDS_PENDING = "forge_balance_holds_pending"
HOLDS_PENDING_AMOUNT = "forge_balance_holds_pending_amount"
USAGE_PENDING = "forge_usage_pending"
REGISTRY_ERRORS = "forge_model_registry_errors"

_PREFIX_LABELS = ("method", "route", "status")


def _declare() -> None:
    REGISTRY.declare(HTTP_REQUESTS, "counter", "HTTP 请求总数", _PREFIX_LABELS)
    REGISTRY.declare(HTTP_DURATION, "histogram", "HTTP 请求耗时（秒）", ("method", "route"))
    REGISTRY.declare(HTTP_INFLIGHT, "gauge", "正在处理的 HTTP 请求数")
    REGISTRY.declare(API_ERRORS, "counter", "业务错误次数（按错误码）", ("code",))
    REGISTRY.declare(HOLDS_PENDING, "gauge", "处于 held 状态的预扣笔数")
    REGISTRY.declare(HOLDS_PENDING_AMOUNT, "gauge", "处于 held 状态的预扣金额合计")
    REGISTRY.declare(USAGE_PENDING, "gauge", "结算状态仍为 pending 的调用数")
    REGISTRY.declare(REGISTRY_ERRORS, "gauge", "LiteLLM 注册失败待对账的部署数")


_declare()

HISTOGRAM_BUCKETS[HTTP_DURATION] = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

_SEGMENT_ID = re.compile(
    r"^(?:\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{16,})$"
)


def route_label(path: str, *, max_segments: int = 4) -> str:
    """把具体 ID 折叠成 `{id}`，并截断层级，控制标签基数。

    `/api/admin/providers/<uuid>/credentials` → `/api/admin/providers/{id}`，
    再长的路径也只保留前四段，避免扫描器制造无限多时间序列。
    """
    parts = [part for part in path.split("/") if part][:max_segments]
    if not parts:
        return "/"
    folded = ["{id}" if _SEGMENT_ID.fullmatch(part) else part for part in parts]
    return ("/" + "/".join(folded))[:96]
