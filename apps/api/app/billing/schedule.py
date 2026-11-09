"""时段定价匹配引擎。

## 格式规范（内部统一格式）

所有上游格式（LiteLLM / OpenRouter / DeepSeek / 阿里云 / 火山方舟）在解析后，
都会被归一化为下面这个"内部统一格式"。**所有时间字段均为 UTC**，时区只影响 weekday 判定。

```json
{
  "timezone": "UTC",              // IANA 时区名，默认 UTC。决定 weekday 判定基准。
  "rules": [
    {
      "label": "off_peak",
      "exclude_holidays": false,   // 可选，true=跳过该规则在法定节假日的匹配
      "holidays_region": "CN",     // exclude_holidays=true 时的节假日库，默认 CN
      "windows": [
        {"hours_utc": "16:30-00:30", "weekdays": [1,2,3,4,5]},
        {"hours_utc": "00:00-00:00", "weekdays": [6,7]}
      ],
      "overrides": {
        "input_token":          {"unit_price": "0.00000015", "cost_price": "0.00000015"},
        "output_token":         {"unit_price": "0.00000060", "cost_price": "0.00000060"},
        "cached_input_token":   {"unit_price": "0.00000004", "cost_price": "0.00000004"}
      }
    }
  ]
}
```

### 时间窗口写法（三种等价写法）

| 写法 | 格式 | 示例 |
|---|---|---|
| `hours_utc` | "HH:MM-HH:MM" 字符串或列表 | `"01:00-04:00"` 或 `["01:00-04:00", "06:00-10:00"]` |
| `utc_start` / `utc_end` | "HHMM" 格式字符串（OpenRouter 新格式） | `"utc_start": "0100", "utc_end": "0400"` |
| `utc_start` / `utc_end` | 整数分钟（0-1440，OpenRouter 旧格式） | `"utc_start": 60, "utc_end": 240` |

所有写法均为**半开区间** [start, end)，可跨午夜。start==end 表示全天。

### weekday 多种写法（统一转 ISO 1-7）

| 写法 | 示例 | 说明 |
|---|---|---|
| ISO 数字 | `[1,2,3,4,5]` | 周一=1，周日=7 |
| 英文字符串 | `["mon","tue","wed","thu","fri"]` | 不区分大小写，可取缩写或全称 |
| 中文字符串 | `["周一","周二",...,"周日"]` | 同上 |
| 布尔值 | 缺省 | 每天 |

### 中国法定节假日

`exclude_holidays: true` 时，规则在法定节假日不匹配。DeepSeek 明确排除中国法定节假日。
内置 2024-2026 年节假日表（含调休工作日），后续年份可手动扩展 `_HOLIDAY_TABLE`。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

# ---------- 中国法定节假日表（2024-2026，含调休） -------------------------------
# 格式：YYYY-MM-DD → "holiday" | "workday" | null
# holiday = 放假（即使是周末也放）
# workday = 调休上班（即使是周末也上）
_HOLIDAY_TABLE: dict[str, dict[str, str]] = {
    "2024": {
        # 元旦
        "2024-01-01": "holiday",
        # 春节
        "2024-02-10": "holiday", "2024-02-11": "holiday", "2024-02-12": "holiday",
        "2024-02-13": "holiday", "2024-02-14": "holiday", "2024-02-15": "holiday",
        "2024-02-16": "holiday", "2024-02-17": "holiday",
        "2024-02-04": "workday", "2024-02-18": "workday",
        # 清明
        "2024-04-04": "holiday", "2024-04-05": "holiday", "2024-04-06": "holiday",
        "2024-04-07": "workday",
        # 劳动节
        "2024-05-01": "holiday", "2024-05-02": "holiday", "2024-05-03": "holiday",
        "2024-05-04": "holiday", "2024-05-05": "holiday",
        "2024-04-28": "workday", "2024-05-11": "workday",
        # 端午
        "2024-06-10": "holiday",
        # 中秋
        "2024-09-15": "holiday", "2024-09-16": "holiday", "2024-09-17": "holiday",
        "2024-09-14": "workday",
        # 国庆
        "2024-10-01": "holiday", "2024-10-02": "holiday", "2024-10-03": "holiday",
        "2024-10-04": "holiday", "2024-10-05": "holiday", "2024-10-06": "holiday",
        "2024-10-07": "holiday",
        "2024-09-29": "workday", "2024-10-12": "workday",
    },
    "2025": {
        # 元旦
        "2025-01-01": "holiday", "2025-01-02": "holiday", "2025-01-03": "holiday",
        "2024-12-29": "workday",
        # 春节
        "2025-01-26": "workday",
        "2025-01-28": "holiday", "2025-01-29": "holiday", "2025-01-30": "holiday",
        "2025-01-31": "holiday", "2025-02-01": "holiday", "2025-02-02": "holiday",
        "2025-02-03": "holiday", "2025-02-04": "holiday",
        "2025-02-08": "workday",
        # 清明
        "2025-04-04": "holiday", "2025-04-05": "holiday", "2025-04-06": "holiday",
        # 劳动节
        "2025-05-01": "holiday", "2025-05-02": "holiday", "2025-05-03": "holiday",
        "2025-05-04": "holiday", "2025-05-05": "holiday",
        "2025-04-27": "workday",
        # 端午
        "2025-05-31": "holiday", "2025-06-01": "holiday", "2025-06-02": "holiday",
        # 中秋+国庆
        "2025-10-01": "holiday", "2025-10-02": "holiday", "2025-10-03": "holiday",
        "2025-10-04": "holiday", "2025-10-05": "holiday", "2025-10-06": "holiday",
        "2025-10-07": "holiday", "2025-10-08": "holiday",
        "2025-09-28": "workday", "2025-10-11": "workday",
    },
    "2026": {
        # 元旦
        "2026-01-01": "holiday", "2026-01-02": "holiday", "2026-01-03": "holiday",
        # 春节
        "2026-02-16": "holiday", "2026-02-17": "holiday", "2026-02-18": "holiday",
        "2026-02-19": "holiday", "2026-02-20": "holiday", "2026-02-21": "holiday",
        "2026-02-22": "holiday",
        "2026-02-14": "workday", "2026-02-28": "workday",
        # 清明
        "2026-04-04": "holiday", "2026-04-05": "holiday", "2026-04-06": "holiday",
        # 劳动节
        "2026-05-01": "holiday", "2026-05-02": "holiday", "2026-05-03": "holiday",
        "2026-05-04": "holiday", "2026-05-05": "holiday",
        "2026-04-26": "workday", "2026-05-09": "workday",
        # 端午
        "2026-06-19": "holiday", "2026-06-20": "holiday", "2026-06-21": "holiday",
        # 中秋
        "2026-09-25": "holiday", "2026-09-26": "holiday", "2026-09-27": "holiday",
        "2026-09-24": "workday",
        # 国庆
        "2026-10-01": "holiday", "2026-10-02": "holiday", "2026-10-03": "holiday",
        "2026-10-04": "holiday", "2026-10-05": "holiday", "2026-10-06": "holiday",
        "2026-10-07": "holiday",
        "2026-10-10": "workday",
    },
}

# weekday 名称 → ISO 数字
_WEEKDAY_NAMES: dict[str, int] = {
    # 英文缩写/全称
    "mon": 1, "monday": 1,
    "tue": 2, "tues": 2, "tuesday": 2,
    "wed": 3, "wednesday": 3,
    "thu": 4, "thur": 4, "thurs": 4, "thursday": 4,
    "fri": 5, "friday": 5,
    "sat": 6, "saturday": 6,
    "sun": 7, "sunday": 7,
    # 中文
    "周一": 1, "星期一": 1,
    "周二": 2, "星期二": 2,
    "周三": 3, "星期三": 3,
    "周四": 4, "星期四": 4,
    "周五": 5, "星期五": 5,
    "周六": 6, "星期六": 6,
    "周日": 7, "星期日": 7, "星期天": 7,
}


# ---------- 节假日判定 --------------------------------------------------------


def _is_chinese_holiday(d: date) -> bool:
    """判断 date 是否为中国法定节假日（holiday），不包括调休工作日。"""
    year = str(d.year)
    if year not in _HOLIDAY_TABLE:
        # 超出表范围：默认按周末=节假日
        return d.isoweekday() >= 6
    key = d.strftime("%Y-%m-%d")
    flag = _HOLIDAY_TABLE[year].get(key)
    if flag == "holiday":
        return True
    if flag == "workday":
        return False  # 调休日，算工作日
    # 表中没有：按常规（周末算节假日）
    return d.isoweekday() >= 6


# ---------- weekday 标准化 ----------------------------------------------------


def _normalize_weekdays(value: object) -> list[int] | None:
    """把各种 weekday 表示统一成 ISO 1-7 列表（周一=1，周日=7）。None 表示每天。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = [value.strip()]
    if isinstance(value, (int, float)):
        value = [int(value)]
    if not isinstance(value, (list, tuple)):
        return None
    out: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            num = int(item)
            if 1 <= num <= 7:
                out.append(num)
            continue
        if isinstance(item, str):
            stripped = item.strip().lower()
            if stripped.isdigit():
                num_val = int(stripped)
                if 1 <= num_val <= 7:
                    out.append(num_val)
            else:
                name_val = _WEEKDAY_NAMES.get(stripped)
                if name_val is not None:
                    out.append(name_val)
                else:
                    name_val2 = _WEEKDAY_NAMES.get(item.strip())
                    if name_val2 is not None:
                        out.append(name_val2)
    return sorted(set(out)) or None


# ---------- 时段解析 ----------------------------------------------------------


def _parse_hhmm(value: object) -> time | None:
    """解析 "HHMM" 格式（OpenRouter）或整数分钟，返回 time 对象。"""
    if isinstance(value, int) and 0 <= value < 1440:
        return time(value // 60, value % 60)
    if isinstance(value, str):
        m = re.fullmatch(r"(\d{4})", value.strip())
        if m:
            hh, mm = int(m.group(1)[:2]), int(m.group(1)[2:])
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return time(hh, mm)
    return None


def _parse_hour_range(spec: str) -> tuple[time, time, bool]:
    """解析 "HH:MM-HH:MM"。返回 (start, end, wraps_midnight)。"""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", spec.strip())
    if not m:
        raise ValueError(f"无效时段格式: {spec!r}")
    sh, sm, eh, em = (int(x) for x in m.groups())
    if not (0 <= sh <= 23 and 0 <= eh <= 23 and 0 <= sm <= 59 and 0 <= em <= 59):
        raise ValueError(f"时段越界: {spec!r}")
    start = time(sh, sm)
    end = time(eh, em)
    wraps = (sh, sm) > (eh, em) or (sh, sm) == (eh, em)  # start==end 视作全天
    return start, end, wraps


def _window_times(window: dict) -> tuple[time, time, bool] | None:
    """从 window dict 提取 (start_time, end_time, wraps_midnight)。"""
    # 写法 1：hours_utc "HH:MM-HH:MM" 或列表
    hours_spec = window.get("hours_utc")
    if isinstance(hours_spec, str):
        try:
            return _parse_hour_range(hours_spec)
        except ValueError:
            return None
    # 写法 2：utc_start / utc_end (OpenRouter)
    us = window.get("utc_start")
    ue = window.get("utc_end")
    if us is not None and ue is not None:
        start = _parse_hhmm(us)
        end = _parse_hhmm(ue)
        if start is None or end is None:
            return None
        wraps = (start.hour, start.minute) >= (end.hour, end.minute)
        return start, end, wraps
    return None


def _is_in_window(moment_utc: datetime, window: dict) -> bool:
    """判断 UTC 时刻是否落在单个时间窗口内（不含 weekday/holiday 判定）。"""
    hours_spec = window.get("hours_utc")
    if isinstance(hours_spec, list):
        return any(_is_in_window(moment_utc, {**window, "hours_utc": s}) for s in hours_spec)
    parsed = _window_times(window)
    if parsed is None:
        return False
    start, end, wraps = parsed
    t = moment_utc.time()
    if wraps:
        return t >= start or t < end
    return start <= t < end


# ---------- weekday / holiday 判定 --------------------------------------------


def _weekday_matches(moment_utc: datetime, weekday_timezone: str, weekdays: list[int] | None) -> bool:
    """判断 weekday。用指定时区判定自然日归属，默认 UTC。"""
    if not weekdays:
        return True
    tz = ZoneInfo(weekday_timezone)
    local = moment_utc.astimezone(tz)
    return local.isoweekday() in set(weekdays)


def _holiday_excludes(
    moment_utc: datetime,
    weekday_timezone: str,
    exclude_holidays: bool,
    holidays_region: str,
) -> bool:
    """
    判断时刻是否应因节假日被排除。
    返回 True = 该时刻落在法定节假日，规则不匹配。
    """
    if not exclude_holidays or holidays_region != "CN":
        return False
    tz = ZoneInfo(weekday_timezone)
    local = moment_utc.astimezone(tz)
    return _is_chinese_holiday(local.date())


# ---------- 主入口 ----------------------------------------------------------


def match_schedule(schedule: dict, at: datetime) -> dict | None:
    """
    根据 UTC 时刻 at 匹配 schedule 规则，返回命中的 overrides dict 或 None。
    多个规则都命中时，取数组中排在最前面的（先写的优先级更高）。

    schedule 格式见模块文档。
    """
    if not schedule or not isinstance(schedule, dict):
        return None
    rules = schedule.get("rules")
    if not isinstance(rules, list):
        return None
    tz_name = schedule.get("timezone") or "UTC"
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        weekdays = _normalize_weekdays(rule.get("weekdays"))
        exclude_h = bool(rule.get("exclude_holidays"))
        h_region = (rule.get("holidays_region") or schedule.get("holidays_region") or "CN").upper()

        matched_any_window = False
        for window in rule.get("windows") or []:
            if not isinstance(window, dict):
                continue
            wd = _normalize_weekdays(window.get("weekdays")) or weekdays
            if not _weekday_matches(at, tz_name, wd):
                continue
            if _holiday_excludes(at, tz_name, exclude_h, h_region):
                continue
            if _is_in_window(at, window):
                matched_any_window = True
                break
        if matched_any_window:
            return rule.get("overrides") if isinstance(rule.get("overrides"), dict) else None
    return None


# ---------- overrides 应用 ---------------------------------------------------


def apply_overrides(
    meters: list[tuple[str, Decimal, Decimal, int]],
    overrides: dict | None,
) -> list[tuple[str, Decimal, Decimal, int]]:
    """
    用 overrides 覆盖基础 meter 价格。
    meters: [(meter, unit_price, cost_price, min_billable_units), ...]
    overrides: {"input_token": {"unit_price": "0.00015", "cost_price": "0.00015"}}
    """
    if not overrides:
        return meters
    out: list[tuple[str, Decimal, Decimal, int]] = []
    for meter, unit, cost, min_bill in meters:
        ov = overrides.get(meter)
        if isinstance(ov, dict):
            ou = Decimal(str(ov["unit_price"])) if "unit_price" in ov else unit
            oc = Decimal(str(ov["cost_price"])) if "cost_price" in ov else cost
            out.append((meter, ou, oc, min_bill))
        else:
            out.append((meter, unit, cost, min_bill))
    return out
