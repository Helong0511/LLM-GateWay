"""请求级数据库会话。成功时提交，异常时回滚。"""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog
from fastapi import Request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError

logger = structlog.get_logger(__name__)


def _constraint_name(exc: IntegrityError) -> str:
    """从数据库异常里取约束名，用于把唯一冲突映射成业务错误码。"""

    original = getattr(exc, "orig", None)
    diag = getattr(original, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if isinstance(name, str):
        return name.lower()
    text = str(original or exc).lower()
    return text


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    maker = getattr(request.app.state, "sessionmaker", None)
    if maker is None:
        raise AppError(503, "DB_NOT_READY")
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except AppError:
            await session.rollback()
            raise
        except IntegrityError as exc:
            await session.rollback()
            constraint = _constraint_name(exc)
            if "users_email_normalized" in constraint:
                raise AppError(409, "EMAIL_TAKEN") from exc
            logger.warning("integrity_conflict", constraint=constraint)
            raise AppError(409, "IDEMPOTENCY_CONFLICT") from exc
        except SQLAlchemyError as exc:
            try:
                await session.rollback()
            except SQLAlchemyError:
                pass
            logger.error("database_unavailable", error_type=type(exc).__name__)
            raise AppError(503, "DB_NOT_READY") from exc
        except Exception:
            await session.rollback()
            raise
