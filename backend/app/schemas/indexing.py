from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.document_index import IndexingStatus


class DocumentIndexResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    status: IndexingStatus
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    indexed_chunk_count: int
    source_extraction_sha256: str
    qdrant_collection: str
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SemanticSearchRequest(BaseModel):
    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
    ]
    case_id: UUID | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class SemanticSearchResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID
    document_id: UUID
    case_id: UUID
    chunk_index: int
    content: str
    score: float
    page_start: int | None
    page_end: int | None
    metadata: dict[str, object]


class SemanticSearchResponse(BaseModel):
    results: list[SemanticSearchResultResponse]
