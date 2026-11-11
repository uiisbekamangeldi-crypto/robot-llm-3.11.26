"""Add a versioned 384-dimensional vector to knowledge chunks.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_chunks", sa.Column("embedding", VECTOR(384), nullable=True))
    op.add_column("knowledge_chunks", sa.Column("embedding_model", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_column("knowledge_chunks", "embedding")
