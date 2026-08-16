from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_extraction import DocumentExtraction


class DocumentExtractionRepository:
    """Persistence operations for the one current extraction per document."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_document_id(self, document_id: UUID) -> DocumentExtraction | None:
        return await self._session.scalar(
            select(DocumentExtraction).where(
                DocumentExtraction.document_id == document_id
            )
        )

    async def create(self, extraction: DocumentExtraction) -> DocumentExtraction:
        self._session.add(extraction)
        await self._session.flush()
        return extraction

    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        self._session.add(extraction)
        await self._session.flush()
        return extraction
