"""Create deterministic document chunks and indexing lifecycle.

Revision ID: 0006_chunk_index
Revises: 0005_document_ocr
Create Date: 2026-08-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_chunk_index"
down_revision: str | None = "0005_document_ocr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

indexing_status = sa.Enum(
    "PENDING", "PROCESSING", "COMPLETED", "FAILED", name="indexing_status"
)


def upgrade() -> None:
    op.create_table(
        "document_indexes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", indexing_status, server_default="PENDING", nullable=False),
        sa.Column("embedding_provider", sa.String(length=50), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("indexed_chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_extraction_sha256", sa.String(length=64), nullable=False),
        sa.Column("qdrant_collection", sa.String(length=255), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name=op.f("fk_document_indexes_document_id_documents"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_indexes")),
    )
    op.create_index(op.f("ix_document_indexes_document_id"), "document_indexes", ["document_id"], unique=True)
    op.create_index(op.f("ix_document_indexes_status"), "document_indexes", ["status"], unique=False)

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("chunk_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"], ["document_extractions.id"],
            name=op.f("fk_document_chunks_extraction_id_document_extractions"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"),
    )
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_chunks_extraction_id"), "document_chunks", ["extraction_id"], unique=False)
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_extraction_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index(op.f("ix_document_indexes_status"), table_name="document_indexes")
    op.drop_index(op.f("ix_document_indexes_document_id"), table_name="document_indexes")
    op.drop_table("document_indexes")
    indexing_status.drop(op.get_bind(), checkfirst=True)
