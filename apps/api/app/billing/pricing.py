"""价格版本。调价新增版本，不改已经生效的单价。

## 三层覆盖关系

1. **阶梯计费**（tier_min_tokens）：同一 meter 有多档时，按 token 数选档。
   tier_min_tokens=0 是基础档，>0 是长输入高档。
   阿里云百炼规则：所有 Token 按所在最高档单价结算。

2. **时段计费**（schedule_rules）：同一时段内 overrides 覆盖基础价。
   overrides 里只写需要改的 meter，没写的继承基础档（含 tier）。

3. **默认价兜底**：publish 时漏传 input_token/output_token → 用平台默认价补齐；
   cost_price 缺失 → 用 unit_price 兜底（防毛利报表 0 成本）。

优先级：基础 tier 价 → 时段 overrides 覆盖 → 默认价兜底。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.money import METERS, format_money, parse_money, q
from app.billing.schedule import match_schedule
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.billing import ModelPrice, PricingVersion
from app.db.models.providers import ModelCatalog


@dataclass(frozen=True)
class MeterInput:
    meter: str
    unit_price: Decimal
    cost_price: Decimal
    min_billable_units: int
    tier_min_tokens: int = 0  # 阶梯计费下限 token 数，0=基础档


@dataclass(frozen=True)
class Quote:
    user_charge: Decimal
    provider_cost: Decimal
    snapshot_json: str


def calculate(
    meters: list[MeterInput],
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
) -> Quote:
    """
    按 token 数计算费用。

    阶梯计费规则：同一 meter 有多档时，取 tier_min_tokens ≤ input_tokens 的最高档。
    例：某模型 input_token 有三档 tier_min_tokens=0/32001/128001，
    请求 200K tokens → 命中 128001 档 → 全部 200K 按该档单价结算。

    时段覆盖由 quote() 在调用前通过 apply_overrides 完成，
    calculate() 只负责按传入的 meter 行做数值计算。
    """
    # 按 meter 分组，每组内按 tier_min_tokens 排序
    by_meter: dict[str, list[MeterInput]] = {}
    for item in meters:
        by_meter.setdefault(item.meter, []).append(item)
    for key in by_meter:
        by_meter[key].sort(key=lambda m: m.tier_min_tokens)

    def _pick_tier(meter: str, tokens: int) -> MeterInput | None:
        tiers = by_meter.get(meter)
        if not tiers:
            return None
        if len(tiers) == 1:
            return tiers[0]
        # 取 tier_min_tokens <= tokens 的最高档
        chosen = tiers[0]
        for t in tiers:
            if t.tier_min_tokens <= tokens:
                chosen = t
            else:
                break
        return chosen

    cached_units = min(max(cached_tokens, 0), max(input_tokens, 0))
    plain_input = max(input_tokens, 0) - cached_units
    user = Decimal("0")
    cost = Decimal("0")
    snapshot: dict[str, str] = {}

    # input_token 和 cached_input_token 共享阶梯判定基准
    input_tier_ref = plain_input if plain_input > 0 else cached_units

    pairs = (
        ("input_token", plain_input, input_tier_ref),
        ("cached_input_token", cached_units, cached_units),
        ("output_token", max(output_tokens, 0), max(output_tokens, 0)),
    )
    for meter, units, tier_ref in pairs:
        price = _pick_tier(meter, tier_ref)
        if price is None and meter == "cached_input_token":
            price = _pick_tier("input_token", tier_ref)
        if price is None or units <= 0:
            continue
        billable = max(units, price.min_billable_units)
        user += price.unit_price * billable
        cost += price.cost_price * billable
        key = f"{meter}@tier{price.tier_min_tokens}" if price.tier_min_tokens > 0 else meter
        snapshot[key] = format_money(price.unit_price)

    return Quote(
        q(user),
        q(cost),
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


class PricingService:
    """
    价格版本发布与查询。

    设计要点：
    - 调价只新增版本，旧版本通过 effective_to 截止。
    - 漏传 input_token / output_token 会用平台默认价补齐，避免"免费跑"。
    - cost_price 缺失时用 unit_price 兜底，防毛利报表 0 成本污染。
    - cached_input_token 由 calculate() 在缺失时回退到 input_token 价格，不主动补。
    """

    REQUIRED_BASE_METERS = ("input_token", "output_token")

    def __init__(self, session: AsyncSession, clock: Clock, settings: Settings) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings

    async def publish(
        self,
        model_id: UUID,
        currency: str,
        meters: list[MeterInput],
        created_by: UUID | None,
        *,
        schedule_rules: dict | None = None,
    ) -> PricingVersion:
        catalog = await self.session.get(ModelCatalog, model_id)
        if catalog is None:
            raise AppError(404, "BILLING_MODEL_NOT_FOUND")
        if not meters:
            raise AppError(400, "PRICE_ITEMS_REQUIRED")

        # 按 meter 分组校验，同一 meter 可以有多档（阶梯）
        groups: dict[str, list[MeterInput]] = {}
        for item in meters:
            if item.meter not in METERS:
                raise AppError(400, "PRICE_METER_INVALID", details={"meter": item.meter})
            if item.min_billable_units < 0:
                raise AppError(400, "PRICE_MIN_UNIT_NEGATIVE")
            if item.tier_min_tokens < 0:
                raise AppError(400, "PRICE_TIER_MIN_NEGATIVE")
            cost = item.cost_price if item.cost_price > 0 else item.unit_price
            groups.setdefault(item.meter, []).append(
                MeterInput(item.meter, item.unit_price, cost, item.min_billable_units, item.tier_min_tokens)
            )

        # 同一 meter 内 tier_min_tokens 不能重复
        for meter, items in groups.items():
            tier_keys = [m.tier_min_tokens for m in items]
            if len(tier_keys) != len(set(tier_keys)):
                raise AppError(400, "PRICE_TIER_DUPLICATE", details={"meter": meter})

        seen_meters = set(groups.keys())

        # 补齐基础 meter：input_token / output_token 必须存在
        if "input_token" not in seen_meters:
            groups["input_token"] = [
                MeterInput(
                    "input_token",
                    q(self.settings.default_model_input_price),
                    q(self.settings.default_model_input_price),
                    0,
                    0,
                )
            ]
        if "output_token" not in seen_meters:
            groups["output_token"] = [
                MeterInput(
                    "output_token",
                    q(self.settings.default_model_output_price),
                    q(self.settings.default_model_output_price),
                    0,
                    0,
                )
            ]

        now = self.clock.now()
        current = await self.active(model_id, currency, at=now)
        if current is not None and current.effective_to is None:
            current.effective_to = now
        version_no = await self._next_version(model_id)
        version = PricingVersion(
            model_id=model_id,
            version=version_no,
            currency=currency,
            effective_from=now,
            effective_to=None,
            created_by=created_by,
            created_at=now,
            schedule_rules=schedule_rules,
        )
        self.session.add(version)
        await self.session.flush()
        for meter_items in groups.values():
            for item in meter_items:
                self.session.add(
                    ModelPrice(
                        pricing_version_id=version.id,
                        meter=item.meter,
                        unit_price=item.unit_price,
                        cost_price=item.cost_price,
                        min_billable_units=item.min_billable_units,
                        tier_min_tokens=item.tier_min_tokens,
                    )
                )
        await self.session.flush()
        return version

    async def active(
        self, model_id: UUID, currency: str, *, at: datetime | None = None
    ) -> PricingVersion | None:
        moment = self.clock.now() if at is None else at
        result = await self.session.execute(
            select(PricingVersion)
            .where(
                PricingVersion.model_id == model_id,
                PricingVersion.currency == currency,
                PricingVersion.effective_from <= moment,
                (PricingVersion.effective_to.is_(None)) | (PricingVersion.effective_to > moment),
            )
            .order_by(PricingVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def quote(
        self,
        version_id: UUID,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        *,
        at: datetime | None = None,
    ) -> Quote:
        """
        按 version 计算费用。

        at: 请求完成的 UTC 时刻。如果 version 上配了 schedule_rules，
            会用它匹配时段覆盖基础 tier 价。None 等同于当前时刻。
        """
        result = await self.session.execute(
            select(PricingVersion).where(PricingVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise AppError(404, "PRICE_VERSION_NOT_FOUND")
        prices = await self.session.execute(
            select(ModelPrice).where(ModelPrice.pricing_version_id == version_id)
        )
        raw_rows = prices.scalars().all()
        if not raw_rows:
            raise AppError(404, "PRICE_VERSION_NOT_FOUND")

        # 时段覆盖：overrides 只改价格，不改 tier 结构
        moment = self.clock.now() if at is None else at
        overrides = match_schedule(version.schedule_rules or {}, moment)

        meters: list[MeterInput] = []
        for row in raw_rows:
            unit = row.unit_price
            cost = row.cost_price
            if overrides:
                ov = overrides.get(row.meter)
                if isinstance(ov, dict):
                    unit = Decimal(str(ov["unit_price"])) if "unit_price" in ov else unit
                    cost = Decimal(str(ov["cost_price"])) if "cost_price" in ov else cost
            meters.append(
                MeterInput(row.meter, unit, cost, row.min_billable_units, row.tier_min_tokens)
            )

        quote = calculate(meters, input_tokens, output_tokens, cached_tokens)

        # 命中时段时把 label 打进 snapshot，方便排障
        if overrides is not None:
            try:
                label = next(
                    (r.get("label") for r in version.schedule_rules.get("rules", []) if isinstance(r, dict)),  # type: ignore[union-attr]
                    "peak",
                )
            except Exception:
                label = "peak"
            data = json.loads(quote.snapshot_json)
            data["schedule"] = label
            quote = Quote(
                quote.user_charge,
                quote.provider_cost,
                json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
        return quote

    @staticmethod
    def meters_from_payload(items: list[dict[str, object]]) -> list[MeterInput]:
        parsed: list[MeterInput] = []
        for item in items:
            meter = item.get("meter")
            unit = item.get("unit_price")
            cost = item.get("cost_price")
            minimum = item.get("min_billable_units", 0)
            tier = item.get("tier_min_tokens", 0)
            if not isinstance(meter, str) or not isinstance(unit, str) or not isinstance(cost, str):
                raise AppError(400, "PRICE_UNIT_BAD_FORMAT")
            if not isinstance(minimum, int):
                raise AppError(400, "PRICE_MIN_UNIT_INT")
            if not isinstance(tier, int):
                raise AppError(400, "PRICE_TIER_MIN_INT")
            parsed.append(MeterInput(meter, parse_money(unit), parse_money(cost), minimum, tier))
        return parsed

    async def _next_version(self, model_id: UUID) -> int:
        result = await self.session.execute(
            select(func.max(PricingVersion.version)).where(PricingVersion.model_id == model_id)
        )
        current = result.scalar_one()
        if current is None:
            return 1
        return int(current) + 1
