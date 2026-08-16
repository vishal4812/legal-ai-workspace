from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer

from app.models.document import DocumentStatus
from app.models.document_extraction import ExtractionStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    sha256_hash: str
    status: DocumentStatus
    is_active: bool
    created_by: UUID
    @field_serializer("created_at", "updated_at")
    def serialize_utc_timestamp(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(DocumentResponse):
    """Metadata returned after both storage publication and DB commit succeed."""


class DocumentExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    extractor_type: str
    extractor_version: str
    status: ExtractionStatus
    text_content: str
    character_count: int
    page_count: int | None
    source_sha256_hash: str
    extracted_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("extracted_at", "created_at", "updated_at")
    def serialize_optional_utc_timestamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
