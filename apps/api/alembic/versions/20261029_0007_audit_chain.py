"""审计事件哈希链。已有记录按时间补上序号和哈希。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from app.admin.audit import GENESIS, event_hash, recorded_stamp

revision: str = "20261029_0007"
down_revision: str | None = "20261028_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("seq", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("recorded_at", sa.String(length=32), nullable=True))
    op.create_table("audit_chain_lock", sa.Column("id", sa.Integer(), primary_key=True))
    op.execute(sa.text("INSERT INTO audit_chain_lock (id) VALUES (1)"))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, actor_id, action, target_type, target_id, detail, created_at "
            "FROM audit_events ORDER BY created_at, id"
        )
    ).mappings()
    prev_hash = GENESIS
    seq = 1
    for row in rows:
        created = row["created_at"]
        if not isinstance(created, datetime):
            created = datetime.fromisoformat(str(created))
        actor = row["actor_id"]
        if isinstance(actor, str):
            actor = UUID(actor)
        stamp = recorded_stamp(created)
        detail = str(row["detail"] or "")
        digest = event_hash(
            seq=seq,
            prev_hash=prev_hash,
            actor_id=actor,
            action=str(row["action"]),
            target_type=str(row["target_type"]),
            target_id=str(row["target_id"]),
            detail=detail,
            recorded_at=stamp,
        )
        bind.execute(
            sa.text(
                "UPDATE audit_events SET seq = :seq, prev_hash = :prev_hash, content_hash = :content_hash, "
                "recorded_at = :recorded_at WHERE id = :id"
            ),
            {
                "seq": seq,
                "prev_hash": prev_hash,
                "content_hash": digest,
                "recorded_at": stamp,
                "id": row["id"],
            },
        )
        prev_hash = digest
        seq += 1
    op.alter_column("audit_events", "seq", nullable=False)
    op.alter_column("audit_events", "prev_hash", nullable=False)
    op.alter_column("audit_events", "content_hash", nullable=False)
    op.alter_column("audit_events", "recorded_at", nullable=False)
    op.create_unique_constraint("uq_audit_events_seq", "audit_events", ["seq"])
    op.create_unique_constraint("uq_audit_events_content_hash", "audit_events", ["content_hash"])
    op.execute(
        """
        CREATE FUNCTION forbid_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION forbid_audit_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS forbid_audit_event_mutation()")
    op.drop_constraint("uq_audit_events_content_hash", "audit_events", type_="unique")
    op.drop_constraint("uq_audit_events_seq", "audit_events", type_="unique")
    op.drop_column("audit_events", "recorded_at")
    op.drop_column("audit_events", "content_hash")
    op.drop_column("audit_events", "prev_hash")
    op.drop_column("audit_events", "seq")
    op.drop_table("audit_chain_lock")
