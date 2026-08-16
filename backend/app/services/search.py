from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingError, EmbeddingProvider
from app.repositories.cases import get_workspace_case
from app.repositories.indexing import DocumentChunkRepository
from app.security.authorization import WorkspaceAccess
from app.services.errors import DomainError
from app.vector.base import VectorStore, VectorStoreError


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk_id: UUID
    document_id: UUID
    case_id: UUID
    chunk_index: int
    content: str
    score: float
    page_start: int | None
    page_end: int | None
    metadata: dict[str, object]


class VectorSearchService:
    def __init__(
        self,
        session: AsyncSession,
        embeddings: EmbeddingProvider,
        vectors: VectorStore,
    ) -> None:
        self._session = session
        self._embeddings = embeddings
        self._vectors = vectors
        self._chunks = DocumentChunkRepository(session)

    async def search(
        self,
        access: WorkspaceAccess,
        query: str,
        case_id: UUID | None,
        top_k: int,
    ) -> list[SearchResult]:
        if case_id is not None:
            legal_case = await get_workspace_case(
                self._session, access.workspace.id, case_id
            )
            if legal_case is None:
                raise DomainError(status.HTTP_404_NOT_FOUND, "Case not found")
        try:
            await self._vectors.ensure_collection(self._embeddings.dimension)
            query_vector = await self._embeddings.embed_query(query)
            hits = await self._vectors.search(
                query_vector,
                access.workspace.id,
                case_id,
                min(top_k * 3, 150),
            )
        except EmbeddingError as exc:
            raise DomainError(
                status.HTTP_503_SERVICE_UNAVAILABLE, exc.safe_message
            ) from exc
        except VectorStoreError as exc:
            raise DomainError(
                status.HTTP_503_SERVICE_UNAVAILABLE, exc.safe_message
            ) from exc

        records = await self._chunks.get_authorized_completed(
            [hit.id for hit in hits], access.workspace.id, case_id
        )
        by_id = {record.chunk.id: record for record in records}
        results: list[SearchResult] = []
        for hit in hits:
            record = by_id.get(hit.id)
            if record is None:
                continue
            chunk = record.chunk
            if hit.payload.get("workspace_id") != str(access.workspace.id):
                continue
            if hit.payload.get("case_id") != str(record.case_id):
                continue
            if hit.payload.get("document_id") != str(record.document.id):
                continue
            if hit.payload.get("content_hash") != chunk.content_hash:
                continue
            if (
                hit.payload.get("extraction_sha256")
                != record.index.source_extraction_sha256
            ):
                continue
            results.append(
                SearchResult(
                    chunk_id=chunk.id,
                    document_id=record.document.id,
                    case_id=record.case_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    score=hit.score,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    metadata=chunk.chunk_metadata,
                )
            )
            if len(results) == top_k:
                break
        return results
