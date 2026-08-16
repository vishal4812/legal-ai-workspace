"""Create persistent document text extractions.

Revision ID: 0004_document_extraction
Revises: 0003_document_vault
Create Date: 2026-08-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_document_extraction"
down_revision: str | None = "0003_document_vault"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

extraction_status = sa.Enum(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="extraction_status",
)


def upgrade() -> None:
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extractor_type", sa.String(length=50), nullable=False),
        sa.Column("extractor_version", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            extraction_status,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("text_content", sa.Text(), server_default="", nullable=False),
        sa.Column("character_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("source_sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_extractions_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_extractions")),
    )
    op.create_index(
        op.f("ix_document_extractions_document_id"),
        "document_extractions",
        ["document_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_document_extractions_status"),
        "document_extractions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_extractions_status"), table_name="document_extractions")
    op.drop_index(
        op.f("ix_document_extractions_document_id"),
        table_name="document_extractions",
    )
    op.drop_table("document_extractions")
    extraction_status.drop(op.get_bind(), checkfirst=True)
