"""Knowledge source, document, version, chunk and ingestion job records.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("repository_url", sa.Text(), nullable=False, unique=True),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_sources.id"), nullable=False
        ),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_review"),
        sa.Column("access_level", sa.Text(), nullable=False, server_default="internal"),
        sa.Column("active_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_id", "source_path", name="uq_document_source_path"),
    )
    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_documents.id"),
            nullable=False,
        ),
        sa.Column("source_commit", sa.String(40), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("document_id", "checksum_sha256", name="uq_document_checksum"),
    )
    op.create_foreign_key(
        "fk_document_active_version",
        "knowledge_documents",
        "knowledge_document_versions",
        ["active_version_id"],
        ["id"],
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_document_versions.id"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("version_id", "chunk_index", name="uq_version_chunk"),
    )
    op.create_index("ix_chunks_version", "knowledge_chunks", ["version_id"])
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_sources.id"), nullable=False
        ),
        sa.Column("source_commit", sa.String(40), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_id", "source_commit", name="uq_job_source_commit"),
    )


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_chunks_version", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_constraint("fk_document_active_version", "knowledge_documents", type_="foreignkey")
    op.drop_table("knowledge_document_versions")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_sources")
