"""内容安全钩子。默认关闭。开启后只存类别和摘要哈希，不存提示词。"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import ContentAuditRecord, ContentSafetySetting


async def record_call(
    session: AsyncSession,
    *,
    user_id: UUID,
    model_name: str,
    request_id: str,
    now: datetime,
) -> None:
    setting = await session.get(ContentSafetySetting, 1)
    if setting is None or not setting.enabled:
        return
    digest = hashlib.sha256(f"{model_name}\n{user_id}\n{request_id}".encode()).hexdigest()
    session.add(
        ContentAuditRecord(
            user_id=user_id,
            model_name=model_name[:128],
            category="call",
            summary_hash=digest,
            created_at=now,
        )
    )
