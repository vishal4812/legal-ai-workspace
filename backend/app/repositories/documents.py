from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    """All document queries preserve the case boundary in their predicates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.flush()
        return document

    async def get_by_id(self, case_id: UUID, document_id: UUID) -> Document | None:
        return await self._session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.case_id == case_id,
            )
        )

    async def list_by_case(self, case_id: UUID) -> list[Document]:
        result = await self._session.scalars(
            select(Document)
            .where(Document.case_id == case_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.all())

    async def archive(self, document: Document) -> Document:
        document.is_active = False
        await self._session.flush()
        return document
