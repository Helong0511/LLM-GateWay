"""备份工具解析与多级回退。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.ops import platform as platform_mod


def test_resolve_pg_dump_uses_configured_path(tmp_path: Path) -> None:
    binary = tmp_path / "pg_dump.exe"
    binary.write_text("", encoding="utf-8")
    settings = Settings(
        admin_init_token_path=str(tmp_path / "admin.sha256"),
        pg_dump_path=str(binary),
    )
    assert platform_mod.resolve_pg_dump(settings) == str(binary)


def test_list_backups_prefers_sql_when_no_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_mod, "_BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr(platform_mod, "resolve_pg_dump", lambda _settings=None: None)
    monkeypatch.setattr(platform_mod, "_docker_bin", lambda: None)
    settings = Settings(
        admin_init_token_path=str(tmp_path / "admin.sha256"),
        database_url="postgresql+asyncpg://forge:forge@127.0.0.1:5432/forge",
        backup_allow_docker=True,
    )
    payload = platform_mod.list_backups(settings)
    assert payload["can_backup"] is True
    assert payload["sql_fallback"] is True
    assert payload["pg_dump"] is False
    assert payload["hint_code"] == "sql_fallback"


def test_list_backups_unavailable_for_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_mod, "_BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr(platform_mod, "resolve_pg_dump", lambda _settings=None: None)
    monkeypatch.setattr(platform_mod, "_docker_bin", lambda: None)
    settings = Settings(
        admin_init_token_path=str(tmp_path / "admin.sha256"),
        database_url="sqlite+aiosqlite:///:memory:",
        backup_allow_docker=True,
    )
    payload = platform_mod.list_backups(settings)
    assert payload["can_backup"] is False
    assert payload["sql_fallback"] is False


@pytest.mark.asyncio
async def test_create_backup_docker_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(platform_mod, "_BACKUP_ROOT", backup_dir)
    monkeypatch.setattr(platform_mod, "resolve_pg_dump", lambda _settings=None: None)
    monkeypatch.setattr(platform_mod, "_docker_bin", lambda: "docker")

    def _fake_docker(
        image: str, host: str, port: str, user: str, password: str, database: str, target: Path
    ) -> None:
        assert image == "postgres:16.10-alpine"
        assert host == "127.0.0.1"
        target.write_bytes(b"PGDUMP")

    monkeypatch.setattr(platform_mod, "_backup_with_docker", _fake_docker)
    settings = Settings(
        admin_init_token_path=str(tmp_path / "admin.sha256"),
        backup_allow_docker=True,
        backup_docker_image="postgres:16.10-alpine",
    )
    result = await platform_mod.create_backup(
        "postgresql+asyncpg://forge:secret@127.0.0.1:5432/forge",
        settings,
    )
    assert result["method"] == "docker"
    assert result["bytes"] == 6
    assert (backup_dir / result["name"]).is_file()


@pytest.mark.asyncio
async def test_create_backup_sql_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(platform_mod, "_BACKUP_ROOT", backup_dir)
    monkeypatch.setattr(platform_mod, "resolve_pg_dump", lambda _settings=None: None)
    monkeypatch.setattr(platform_mod, "_docker_bin", lambda: None)

    async def _fake_sql(
        host: str, port: str, user: str, password: str, database: str, target: Path
    ) -> None:
        assert database == "forge"
        target.write_text("-- sql\n", encoding="utf-8")

    monkeypatch.setattr(platform_mod, "_backup_with_sql", _fake_sql)
    settings = Settings(
        admin_init_token_path=str(tmp_path / "admin.sha256"),
        backup_allow_docker=True,
    )
    result = await platform_mod.create_backup(
        "postgresql://forge:secret@127.0.0.1:5432/forge",
        settings,
    )
    assert result["method"] == "sql"
    assert str(result["name"]).endswith(".sql")


@pytest.mark.asyncio
async def test_create_backup_rejects_non_postgres(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_mod, "_BACKUP_ROOT", tmp_path / "backups")
    with pytest.raises(AppError) as exc:
        await platform_mod.create_backup(
            "sqlite+aiosqlite:///:memory:",
            Settings(admin_init_token_path=str(tmp_path / "admin.sha256")),
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_create_backup_encrypts_and_removes_plaintext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cryptography.fernet import Fernet

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(platform_mod, "_BACKUP_ROOT", backup_dir)
    monkeypatch.setattr(platform_mod, "resolve_pg_dump", lambda _settings=None: None)
    monkeypatch.setattr(platform_mod, "_docker_bin", lambda: None)

    async def _fake_sql(
        host: str, port: str, user: str, password: str, database: str, target: Path
    ) -> None:
        target.write_bytes(b"-- sql\n")

    monkeypatch.setattr(platform_mod, "_backup_with_sql", _fake_sql)
    key = Fernet.generate_key().decode()
    settings = Settings(
        admin_init_token_path=str(tmp_path / "admin.sha256"),
        backup_allow_docker=True,
        backup_encryption_key=key,
    )
    result = await platform_mod.create_backup(
        "postgresql://forge:secret@127.0.0.1:5432/forge",
        settings,
    )

    assert result["encrypted"] is True
    assert str(result["name"]).endswith(".sql.enc")
    sealed = backup_dir / str(result["name"])
    assert Fernet(key.encode()).decrypt(sealed.read_bytes()) == b"-- sql\n"
    # 明文必须被删除：留着等于没加密
    assert not (backup_dir / f"{str(result['name']).removesuffix('.enc')}").exists()

    listed = platform_mod.list_backups(settings)
    assert str(result["name"]) in [item["name"] for item in listed["backups"]]
    platform_mod.delete_backup(str(result["name"]))
    assert not sealed.exists()


@pytest.mark.asyncio
async def test_invalid_backup_key_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(platform_mod, "_BACKUP_ROOT", backup_dir)
    monkeypatch.setattr(platform_mod, "resolve_pg_dump", lambda _settings=None: None)
    monkeypatch.setattr(platform_mod, "_docker_bin", lambda: None)

    async def _fake_sql(
        host: str, port: str, user: str, password: str, database: str, target: Path
    ) -> None:
        target.write_text("-- sql\n", encoding="utf-8")

    monkeypatch.setattr(platform_mod, "_backup_with_sql", _fake_sql)
    settings = Settings(
        admin_init_token_path=str(tmp_path / "admin.sha256"),
        backup_allow_docker=True,
        backup_encryption_key="not-a-fernet-key",
    )
    with pytest.raises(AppError) as exc:
        await platform_mod.create_backup(
            "postgresql://forge:secret@127.0.0.1:5432/forge",
            settings,
        )
    assert exc.value.code == "BACKUP_ENCRYPTION_KEY_INVALID"
