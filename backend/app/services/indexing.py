from __future__ import annotations

import hashlib
import logging
from time import monotonic
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingError, EmbeddingProvider
from app.documents.chunking.base import Chunker
from app.models.document_chunk import DocumentChunk
from app.models.document_extraction import ExtractionStatus
from app.models.document_index import DocumentIndex, IndexingStatus
from app.models.user import utc_now
from app.repositories.extractions import DocumentExtractionRepository
from app.repositories.indexing import DocumentChunkRepository, DocumentIndexRepository
from app.security.authorization import DocumentAccess
from app.services.errors import DomainError
from app.vector.base import VectorPoint, VectorStore, VectorStoreError

LOGGER = logging.getLogger(__name__)


class DocumentIndexingService:
    """Coordinate deterministic PostgreSQL chunks and replaceable Qdrant points."""

    def __init__(
        self,
        session: AsyncSession,
        chunker: Chunker,
        embeddings: EmbeddingProvider,
        vectors: VectorStore,
        embedding_batch_size: int,
    ) -> None:
        self._session = session
        self._chunker = chunker
        self._embeddings = embeddings
        self._vectors = vectors
        self._embedding_batch_size = embedding_batch_size
        self._indexes = DocumentIndexRepository(session)
        self._chunks = DocumentChunkRepository(session)
        self._extractions = DocumentExtractionRepository(session)

    async def get(self, access: DocumentAccess) -> DocumentIndex:
        document_index = await self._indexes.get_by_document_id(access.document.id)
        if document_index is None:
            raise DomainError(status.HTTP_404_NOT_FOUND, "Document index not found")
        return document_index

    async def index(self, access: DocumentAccess) -> DocumentIndex:
        document = access.document
        extraction = await self._extractions.get_by_document_id(document.id)
        if extraction is None:
            raise DomainError(
                status.HTTP_409_CONFLICT,
                "Complete document extraction before indexing",
            )
        if extraction.status != ExtractionStatus.COMPLETED:
            raise DomainError(
                status.HTTP_409_CONFLICT,
                "Document extraction is not completed",
            )
        if extraction.source_sha256_hash != document.sha256_hash:
            raise DomainError(
                status.HTTP_409_CONFLICT,
                "Document extraction does not match the retained original",
            )

        extraction_hash = hashlib.sha256(extraction.text_content.encode("utf-8")).hexdigest()
        document_index = await self._indexes.get_by_document_id(document.id)
        if self._is_current(document_index, extraction_hash):
            assert document_index is not None
            return document_index
        if document_index is not None and document_index.status in {
            IndexingStatus.PENDING,
            IndexingStatus.PROCESSING,
        }:
            raise DomainError(
                status.HTTP_409_CONFLICT,
                "Document indexing is already in progress",
            )

        try:
            if document_index is None:
                document_index = DocumentIndex(
                    document_id=document.id,
                    status=IndexingStatus.PENDING,
                    embedding_provider=self._embeddings.provider_name,
                    embedding_model=self._embeddings.model_name,
                    embedding_dimension=self._embeddings.dimension,
                    indexed_chunk_count=0,
                    source_extraction_sha256=extraction_hash,
                    qdrant_collection=self._vectors.collection_name,
                )
                await self._indexes.create(document_index)
            else:
                self._reset(document_index, extraction_hash)
                await self._indexes.save(document_index)
            await self._session.commit()

            document_index.status = IndexingStatus.PROCESSING
            document_index.started_at = utc_now()
            await self._indexes.save(document_index)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            LOGGER.error(
                "document_indexing_persistence_failed workspace_id=%s case_id=%s "
                "document_id=%s stage=prepare category=%s",
                access.case_access.workspace_access.workspace.id,
                access.case_access.case.id,
                document.id,
                type(exc).__name__,
            )
            raise DomainError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Unable to start document indexing",
            ) from exc

        started_at = monotonic()
        try:
            generated = self._chunker.chunk(extraction.text_content)
            source_type = "pdf" if document.mime_type == "application/pdf" else "docx"
            extraction_method = extraction.parser_metadata.get("method", "direct_text")
            chunks = [
                DocumentChunk(
                    document_id=document.id,
                    extraction_id=extraction.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    content_hash=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                    character_count=len(chunk.content),
                    token_count=chunk.token_count,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_metadata={
                        "workspace_id": str(access.case_access.workspace_access.workspace.id),
                        "case_id": str(access.case_access.case.id),
                        "document_id": str(document.id),
                        "chunk_index": chunk.index,
                        "source_type": source_type,
                        "extraction_method": extraction_method,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                    },
                )
                for chunk in generated
            ]
            await self._chunks.replace_for_document(document.id, chunks)
            await self._session.commit()

            all_vectors: list[list[float]] = []
            for offset in range(0, len(chunks), self._embedding_batch_size):
                batch = chunks[offset : offset + self._embedding_batch_size]
                all_vectors.extend(
                    await self._embeddings.embed_texts([chunk.content for chunk in batch])
                )
            await self._vectors.ensure_collection(self._embeddings.dimension)
            points = [
                VectorPoint(
                    id=chunk.id,
                    vector=vector,
                    payload={
                        "workspace_id": str(access.case_access.workspace_access.workspace.id),
                        "case_id": str(access.case_access.case.id),
                        "document_id": str(document.id),
                        "chunk_id": str(chunk.id),
                        "chunk_index": chunk.chunk_index,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "content_hash": chunk.content_hash,
                        "extraction_sha256": extraction_hash,
                        "source_type": source_type,
                        "extraction_method": extraction_method,
                    },
                )
                for chunk, vector in zip(chunks, all_vectors, strict=True)
            ]
            await self._vectors.replace_document_points(document.id, points)
            stored_count = await self._vectors.count_document_points(document.id)
            if stored_count != len(chunks):
                raise VectorStoreError(
                    "QDRANT_POINT_COUNT_MISMATCH",
                    "The document vector index could not be verified",
                )

            document_index.status = IndexingStatus.COMPLETED
            document_index.indexed_chunk_count = len(chunks)
            document_index.completed_at = utc_now()
            document_index.error_code = None
            document_index.error_message = None
            await self._indexes.save(document_index)
            await self._session.commit()
            await self._session.refresh(document_index)
            LOGGER.info(
                "document_indexing_succeeded workspace_id=%s case_id=%s document_id=%s "
                "index_id=%s status=COMPLETED chunk_count=%s embedding_model=%s "
                "duration_seconds=%.3f",
                access.case_access.workspace_access.workspace.id,
                access.case_access.case.id,
                document.id,
                document_index.id,
                len(chunks),
                self._embeddings.model_name,
                monotonic() - started_at,
            )
            return document_index
        except (EmbeddingError, VectorStoreError) as exc:
            await self._record_failure(
                document.id,
                exc.code,
                exc.safe_message,
                started_at,
                access.case_access.workspace_access.workspace.id,
                access.case_access.case.id,
            )
            raise DomainError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Document indexing failed",
            ) from exc
        except Exception as exc:
            await self._record_failure(
                document.id,
                "INDEXING_FAILED",
                "The document could not be indexed",
                started_at,
                access.case_access.workspace_access.workspace.id,
                access.case_access.case.id,
            )
            raise DomainError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Unable to complete document indexing",
            ) from exc

    def _is_current(
        self, document_index: DocumentIndex | None, extraction_hash: str
    ) -> bool:
        return bool(
            document_index is not None
            and document_index.status == IndexingStatus.COMPLETED
            and document_index.source_extraction_sha256 == extraction_hash
            and document_index.embedding_provider == self._embeddings.provider_name
            and document_index.embedding_model == self._embeddings.model_name
            and document_index.embedding_dimension == self._embeddings.dimension
            and document_index.qdrant_collection == self._vectors.collection_name
        )

    def _reset(self, document_index: DocumentIndex, extraction_hash: str) -> None:
        document_index.status = IndexingStatus.PENDING
        document_index.embedding_provider = self._embeddings.provider_name
        document_index.embedding_model = self._embeddings.model_name
        document_index.embedding_dimension = self._embeddings.dimension
        document_index.indexed_chunk_count = 0
        document_index.source_extraction_sha256 = extraction_hash
        document_index.qdrant_collection = self._vectors.collection_name
        document_index.error_code = None
        document_index.error_message = None
        document_index.started_at = None
        document_index.completed_at = None

    async def _record_failure(
        self,
        document_id: UUID,
        code: str,
        message: str,
        started_at: float,
        workspace_id: UUID,
        case_id: UUID,
    ) -> None:
        await self._session.rollback()
        try:
            document_index = await self._indexes.get_by_document_id(document_id)
            if document_index is not None:
                document_index.status = IndexingStatus.FAILED
                document_index.indexed_chunk_count = 0
                document_index.completed_at = None
                document_index.error_code = code
                document_index.error_message = message
                await self._indexes.save(document_index)
                await self._session.commit()
        except Exception as persistence_error:
            await self._session.rollback()
            LOGGER.error(
                "document_indexing_failure_persistence_failed document_id=%s category=%s",
                document_id,
                type(persistence_error).__name__,
            )
        LOGGER.error(
            "document_indexing_failed workspace_id=%s case_id=%s document_id=%s "
            "status=FAILED error_code=%s embedding_model=%s duration_seconds=%.3f",
            workspace_id,
            case_id,
            document_id,
            code,
            self._embeddings.model_name,
            monotonic() - started_at,
        )
