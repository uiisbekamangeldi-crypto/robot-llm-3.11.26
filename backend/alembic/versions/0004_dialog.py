"""Dialog sessions and persistent turns.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dialog_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "dialog_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("dialog_sessions.id")),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("sources", JSONB(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dialog_turns_session", "dialog_turns", ["session_id"])
    op.create_index("ix_dialog_turns_created", "dialog_turns", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_dialog_turns_created", table_name="dialog_turns")
    op.drop_index("ix_dialog_turns_session", table_name="dialog_turns")
    op.drop_table("dialog_turns")
    op.drop_table("dialog_sessions")
