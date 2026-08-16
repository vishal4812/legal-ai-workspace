"""Add structured parser metadata for local OCR provenance.

Revision ID: 0005_document_ocr
Revises: 0004_document_extraction
Create Date: 2026-08-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_document_ocr"
down_revision: str | None = "0004_document_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_extractions",
        sa.Column(
            "parser_metadata",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("document_extractions", "parser_metadata")
