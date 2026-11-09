"""只读/运维：路由一览、公开配置、备份、内容开关和任务记录。"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import UUID

import asyncpg
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.auth.tokens import as_utc
from app.core.config import Settings
from app.core.errors import AppError
from app.core.paging import clamp_page, page_meta, page_offset
from app.db.models.ops import ContentAuditRecord, ContentSafetySetting, JobRun
from app.db.models.providers import ModelCatalog, ModelDeployment, Provider

KNOWN_JOBS = (
    "worker_ping",
    "release_expired_holds",
    "close_expired_payments",
    "verify_audit_chain",
)

_BACKUP_ROOT = Path(__file__).resolve().parents[4] / "backups"

_WIN_PG_DUMP_CANDIDATES = (
    r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\14\bin\pg_dump.exe",
    r"C:\Program Files\PostgreSQL\13\bin\pg_dump.exe",
)


def public_settings(settings: Settings) -> dict[str, object]:
    return {
        "app_env": settings.app_env,
        "operating_mode": settings.operating_mode,
        "mock_payments_enabled": settings.mock_payments_enabled,
        "demo_models_enabled": settings.demo_models_enabled,
        "hold_ttl_seconds": settings.hold_ttl_seconds,
        "payment_ttl_seconds": settings.payment_ttl_seconds,
        "session_idle_hours": settings.session_idle_hours,
        "session_absolute_hours": settings.session_absolute_hours,
        "usdt_min_amount": format(settings.usdt_min_amount, "f"),
        "rate_deviation_limit": format(settings.rate_deviation_limit, "f"),
        "max_body_bytes": settings.max_body_bytes,
    }


async def list_routes(
    session: AsyncSession,
    *,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    """模型调用路由一览：公开名 → 供应商；可按部署状态筛选，并可在后台启停部署。"""
    page, page_size = clamp_page(page, page_size)
    if status is not None and status not in {"", "all", "active", "disabled"}:
        raise AppError(400, "STATUS_FILTER_INVALID")

    filters = [ModelCatalog.status == "published"]
    if status in {"active", "disabled"}:
        filters.append(ModelDeployment.status == status)
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        filters.append(
            or_(
                ModelCatalog.public_name.ilike(like),
                ModelCatalog.display_name.ilike(like),
                Provider.name.ilike(like),
            )
        )

    total = int(
        await session.scalar(
            select(func.count())
            .select_from(ModelDeployment)
            .join(ModelCatalog, ModelCatalog.id == ModelDeployment.model_id)
            .join(Provider, Provider.id == ModelDeployment.provider_id)
            .where(*filters)
        )
        or 0
    )
    statement = (
        select(
            ModelDeployment.id,
            ModelCatalog.public_name,
            ModelCatalog.display_name,
            ModelCatalog.status,
            ModelDeployment.status,
            Provider.id,
            Provider.name,
            Provider.status,
            Provider.priority,
            Provider.weight,
            Provider.base_url,
        )
        .join(ModelCatalog, ModelCatalog.id == ModelDeployment.model_id)
        .join(Provider, Provider.id == ModelDeployment.provider_id)
        .where(*filters)
        .order_by(Provider.priority.asc(), Provider.weight.desc(), ModelCatalog.public_name.asc())
        .offset(page_offset(page, page_size))
        .limit(page_size)
    )
    rows = await session.execute(statement)
    return {
        **page_meta(page, page_size, total),
        "routes": [
            {
                "deployment_id": str(deployment_id),
                "model": public_name,
                "display_name": display_name or public_name,
                "model_status": model_status,
                "status": deployment_status,
                "provider_id": str(provider_id),
                "provider": provider_name,
                "provider_status": provider_status,
                "priority": priority,
                "weight": weight,
                "base_url": base_url,
                "callable": deployment_status == "active" and provider_status == "active",
            }
            for (
                deployment_id,
                public_name,
                display_name,
                model_status,
                deployment_status,
                provider_id,
                provider_name,
                provider_status,
                priority,
                weight,
                base_url,
            ) in rows.all()
        ],
    }


async def content_view(
    session: AsyncSession, *, page: int = 1, page_size: int = 20
) -> dict[str, object]:
    page, page_size = clamp_page(page, page_size)
    setting = await session.get(ContentSafetySetting, 1)
    total = int(await session.scalar(select(func.count()).select_from(ContentAuditRecord)) or 0)
    records = await session.scalars(
        select(ContentAuditRecord)
        .order_by(ContentAuditRecord.created_at.desc(), ContentAuditRecord.id.desc())
        .offset(page_offset(page, page_size))
        .limit(page_size)
    )
    return {
        "enabled": bool(setting and setting.enabled),
        **page_meta(page, page_size, total),
        "records": [
            {
                "id": str(row.id),
                "model_name": row.model_name,
                "category": row.category,
                "summary_hash": row.summary_hash,
                "created_at": as_utc(row.created_at).isoformat(),
            }
            for row in records.all()
        ],
    }


async def set_content_enabled(
    session: AsyncSession,
    actor_id: UUID,
    enabled: bool,
    now: datetime,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    setting = await session.get(ContentSafetySetting, 1)
    if setting is None:
        setting = ContentSafetySetting(id=1, enabled=enabled)
        session.add(setting)
    else:
        setting.enabled = enabled
    await append_audit(
        session,
        actor_id=actor_id,
        action="content.enabled",
        target_type="content_safety",
        target_id="1",
        detail="on" if enabled else "off",
        now=now,
    )
    await session.flush()
    return await content_view(session, page=page, page_size=page_size)


async def list_jobs(
    session: AsyncSession, *, page: int = 1, page_size: int = 20
) -> dict[str, object]:
    page, page_size = clamp_page(page, page_size)
    total = int(await session.scalar(select(func.count()).select_from(JobRun)) or 0)
    failed_total = int(
        await session.scalar(
            select(func.count()).select_from(JobRun).where(JobRun.status == "failed")
        )
        or 0
    )
    rows = await session.scalars(
        select(JobRun)
        .order_by(JobRun.created_at.desc(), JobRun.id.desc())
        .offset(page_offset(page, page_size))
        .limit(page_size)
    )
    runs = [
        {
            "id": str(row.id),
            "name": row.name,
            "status": row.status,
            "detail": row.detail,
            "created_at": as_utc(row.created_at).isoformat(),
        }
        for row in rows.all()
    ]
    failed_rows = await session.scalars(
        select(JobRun)
        .where(JobRun.status == "failed")
        .order_by(JobRun.created_at.desc(), JobRun.id.desc())
        .offset(page_offset(page, page_size))
        .limit(page_size)
    )
    return {
        "jobs": list(KNOWN_JOBS),
        **page_meta(page, page_size, total),
        "runs": runs,
        "failed_total": failed_total,
        "failed": [
            {
                "id": str(row.id),
                "name": row.name,
                "status": row.status,
                "detail": row.detail,
                "created_at": as_utc(row.created_at).isoformat(),
            }
            for row in failed_rows.all()
        ],
    }


async def record_ping(
    session: AsyncSession, detail: str, now: datetime, *, page: int = 1, page_size: int = 20
) -> dict[str, object]:
    session.add(JobRun(name="worker_ping", status="succeeded", detail=detail[:256], created_at=now))
    await session.flush()
    return await list_jobs(session, page=page, page_size=page_size)


def resolve_pg_dump(settings: Settings | None = None) -> str | None:
    configured = (settings.pg_dump_path if settings else "") or ""
    configured = configured.strip().strip('"')
    if configured:
        path = Path(configured)
        if path.is_file():
            return str(path)
    found = shutil.which("pg_dump") or shutil.which("pg_dump.exe")
    if found:
        return found
    if platform.system() == "Windows":
        for candidate in _WIN_PG_DUMP_CANDIDATES:
            if Path(candidate).is_file():
                return candidate
    return None


def _docker_bin() -> str | None:
    return shutil.which("docker") or shutil.which("docker.exe")


def _is_postgres_url(database_url: str) -> bool:
    scheme = urlparse(database_url.replace("postgresql+asyncpg", "postgresql", 1)).scheme.lower()
    return scheme in {"postgresql", "postgres"}


def _list_backup_files() -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for pattern in ("*.dump", "*.sql"):
        for path in _BACKUP_ROOT.glob(pattern):
            if not path.is_file():
                continue
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                }
            )
    files.sort(key=lambda item: str(item["modified_at"]), reverse=True)
    return files


def list_backups(settings: Settings | None = None) -> dict[str, object]:
    _BACKUP_ROOT.mkdir(exist_ok=True)
    files = _list_backup_files()
    pg_dump = resolve_pg_dump(settings)
    docker_ok = _docker_bin() is not None
    allow_docker = True if settings is None else settings.backup_allow_docker
    database_url = settings.database_url if settings else ""
    sql_ok = _is_postgres_url(database_url)
    can_backup = pg_dump is not None or (allow_docker and docker_ok) or sql_ok
    # 稳定码；文案由前端按语言渲染
    if pg_dump is not None:
        hint_code = "local_pg_dump"
    elif allow_docker and docker_ok:
        hint_code = "docker"
    elif sql_ok:
        hint_code = "sql_fallback"
    else:
        hint_code = "unavailable"
    return {
        "backups": files,
        "pg_dump": pg_dump is not None,
        "pg_dump_path": pg_dump,
        "docker_available": docker_ok,
        "backup_allow_docker": allow_docker,
        "sql_fallback": sql_ok,
        "can_backup": can_backup,
        "backup_dir": str(_BACKUP_ROOT),
        "hint_code": hint_code,
    }


def _parse_db(database_url: str) -> tuple[str, str, str, str, str]:
    if not _is_postgres_url(database_url):
        raise AppError(503, "BACKUP_NOT_POSTGRES")
    parsed = urlparse(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    database = unquote(parsed.path.lstrip("/"))
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or 5432)
    if not database or not user:
        raise AppError(503, "BACKUP_DB_URL_INCOMPLETE")
    return host, port, user, password, database


def _run_pg_dump(command: list[str], env: dict[str, str], target: Path) -> None:
    try:
        completed = subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=180, check=False
        )
    except FileNotFoundError as exc:
        target.unlink(missing_ok=True)
        raise AppError(503, "BACKUP_TOOL_MISSING") from exc
    except subprocess.TimeoutExpired as exc:
        target.unlink(missing_ok=True)
        raise AppError(503, "BACKUP_TIMEOUT") from exc
    if completed.returncode != 0:
        target.unlink(missing_ok=True)
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        tip = detail[-1][:200] if detail else "无详细输出"
        raise AppError(503, "BACKUP_FAILED", details={"tip": tip})


def _backup_with_local_pg_dump(
    binary: str, host: str, port: str, user: str, password: str, database: str, target: Path
) -> None:
    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password
    command = [
        binary,
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        database,
        "-F",
        "c",
        "-f",
        str(target),
    ]
    _run_pg_dump(command, env, target)


def _backup_with_docker(
    image: str, host: str, port: str, user: str, password: str, database: str, target: Path
) -> None:
    docker = _docker_bin()
    if docker is None:
        raise AppError(503, "BACKUP_DOCKER_MISSING")
    docker_host = host
    if host in {"127.0.0.1", "localhost"}:
        docker_host = "host.docker.internal"
    env = os.environ.copy()
    command = [docker, "run", "--rm"]
    if platform.system() == "Linux" and docker_host == "host.docker.internal":
        command.append("--add-host=host.docker.internal:host-gateway")
    command.extend(
        [
            "-e",
            f"PGPASSWORD={password}",
            "-v",
            f"{_BACKUP_ROOT.resolve()}:/backups",
            image,
            "pg_dump",
            "-h",
            docker_host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            database,
            "-F",
            "c",
            "-f",
            f"/backups/{target.name}",
        ]
    )
    _run_pg_dump(command, env, target)


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return format(value, "f") if isinstance(value, Decimal) else str(value)
    if isinstance(value, UUID):
        return f"'{value}'"
    if isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    if isinstance(value, time):
        return f"'{value.isoformat()}'"
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return r"'\x" + bytes(value).hex() + "'"
    if isinstance(value, (dict, list)):
        dumped = json.dumps(value, ensure_ascii=False)
        return "'" + dumped.replace("'", "''") + "'::jsonb"
    text = str(value).replace("'", "''")
    return f"'{text}'"


async def _backup_with_sql(
    host: str, port: str, user: str, password: str, database: str, target: Path
) -> None:
    try:
        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001 — 转成对用户可读的运维错误
        target.unlink(missing_ok=True)
        raise AppError(503, "BACKUP_SQL_CONNECT_FAILED", details={"error": type(exc).__name__}) from exc
    try:
        tables = await conn.fetch(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        lines: list[str] = [
            "-- Forge SQL logical backup (not a full pg_dump)",
            f"-- generated_at={datetime.now(UTC).isoformat()}",
            f"-- database={database}",
            "BEGIN;",
            "SET session_replication_role = replica;",
        ]
        for row in tables:
            name = str(row["tablename"])
            lines.append(f'TRUNCATE TABLE "{name}" CASCADE;')
        for row in tables:
            name = str(row["tablename"])
            columns = await conn.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                ORDER BY ordinal_position
                """,
                name,
            )
            if not columns:
                continue
            col_list = ", ".join(f'"{c["column_name"]}"' for c in columns)
            records = await conn.fetch(f'SELECT {col_list} FROM "{name}"')
            for rec in records:
                values = ", ".join(_sql_literal(rec[c["column_name"]]) for c in columns)
                lines.append(f'INSERT INTO "{name}" ({col_list}) VALUES ({values});')
        lines.append("SET session_replication_role = DEFAULT;")
        lines.append("COMMIT;")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise AppError(503, "BACKUP_SQL_FAILED", details={"error": type(exc).__name__}) from exc
    finally:
        await conn.close()


async def create_backup(database_url: str, settings: Settings | None = None) -> dict[str, object]:
    host, port, user, password, database = _parse_db(database_url)
    _BACKUP_ROOT.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    binary = resolve_pg_dump(settings)
    method = "pg_dump"
    if binary is not None:
        target = _BACKUP_ROOT / f"forge-{stamp}.dump"
        await asyncio.to_thread(
            _backup_with_local_pg_dump, binary, host, port, user, password, database, target
        )
    else:
        allow_docker = True if settings is None else settings.backup_allow_docker
        if allow_docker and _docker_bin() is not None:
            target = _BACKUP_ROOT / f"forge-{stamp}.dump"
            image = (settings.backup_docker_image if settings else None) or "postgres:16.10-alpine"
            method = "docker"
            await asyncio.to_thread(
                _backup_with_docker, image, host, port, user, password, database, target
            )
        else:
            target = _BACKUP_ROOT / f"forge-{stamp}.sql"
            method = "sql"
            await _backup_with_sql(host, port, user, password, database, target)
    if not target.is_file() or target.stat().st_size <= 0:
        target.unlink(missing_ok=True)
        raise AppError(503, "BACKUP_EMPTY_FILE")
    return {
        "name": target.name,
        "bytes": target.stat().st_size,
        "method": method,
        "modified_at": datetime.fromtimestamp(target.stat().st_mtime, tz=UTC).isoformat(),
    }


def delete_backup(name: str) -> dict[str, object]:
    cleaned = Path(name).name
    if cleaned != name or ".." in cleaned or not (cleaned.endswith(".dump") or cleaned.endswith(".sql")):
        raise AppError(400, "BACKUP_NAME_INVALID")
    target = _BACKUP_ROOT / cleaned
    if not target.is_file():
        raise AppError(404, "BACKUP_FILE_NOT_FOUND")
    target.unlink()
    return {"name": cleaned, "deleted": True}
