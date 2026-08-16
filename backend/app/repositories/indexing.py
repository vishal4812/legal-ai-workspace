from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_index import DocumentIndex, IndexingStatus


@dataclass(frozen=True, slots=True)
class AuthorizedChunk:
    chunk: DocumentChunk
    document: Document
    index: DocumentIndex
    case_id: UUID


class DocumentIndexRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_document_id(self, document_id: UUID) -> DocumentIndex | None:
        return await self._session.scalar(
            select(DocumentIndex).where(DocumentIndex.document_id == document_id)
        )

    async def create(self, document_index: DocumentIndex) -> DocumentIndex:
        self._session.add(document_index)
        await self._session.flush()
        return document_index

    async def save(self, document_index: DocumentIndex) -> DocumentIndex:
        self._session.add(document_index)
        await self._session.flush()
        return document_index


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_document(
        self, document_id: UUID, chunks: list[DocumentChunk]
    ) -> list[DocumentChunk]:
        await self._session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        self._session.add_all(chunks)
        await self._session.flush()
        return chunks

    async def list_for_document(self, document_id: UUID) -> list[DocumentChunk]:
        result = await self._session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result)

    async def get_authorized_completed(
        self,
        chunk_ids: list[UUID],
        workspace_id: UUID,
        case_id: UUID | None = None,
    ) -> list[AuthorizedChunk]:
        if not chunk_ids:
            return []
        statement = (
            select(DocumentChunk, Document, DocumentIndex, Case.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(Case, Case.id == Document.case_id)
            .join(DocumentIndex, DocumentIndex.document_id == Document.id)
            .where(
                DocumentChunk.id.in_(chunk_ids),
                Case.workspace_id == workspace_id,
                DocumentIndex.status == IndexingStatus.COMPLETED,
            )
        )
        if case_id is not None:
            statement = statement.where(Case.id == case_id)
        rows = (await self._session.execute(statement)).all()
        return [
            AuthorizedChunk(chunk=chunk, document=document, index=index, case_id=row_case_id)
            for chunk, document, index, row_case_id in rows
        ]
