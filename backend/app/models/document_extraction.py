from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utc_now

if TYPE_CHECKING:
    from app.models.document import Document


class ExtractionStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"),
        unique=True,
        index=True,
        nullable=False,
    )
    extractor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ExtractionStatus] = mapped_column(
        SqlEnum(ExtractionStatus, name="extraction_status", native_enum=True),
        default=ExtractionStatus.PENDING,
        server_default=ExtractionStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    text_content: Mapped[str] = mapped_column(Text(), default="", server_default="", nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    source_sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped["Document"] = relationship(back_populates="extraction")
