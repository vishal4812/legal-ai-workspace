from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extractors.base import DocumentExtractor, ExtractionError
from app.documents.extractors.docx import DOCXExtractor
from app.documents.extractors.normalization import render_extracted_text
from app.documents.extractors.pdf import PDFExtractor
from app.models.document_extraction import DocumentExtraction, ExtractionStatus
from app.models.user import utc_now
from app.repositories.extractions import DocumentExtractionRepository
from app.security.authorization import DocumentAccess
from app.services.errors import DomainError
from app.storage.base import StorageProvider
from app.storage.local import InvalidStorageKeyError, StorageError

LOGGER = logging.getLogger(__name__)


class DocumentExtractionService:
    """Run local extractors without coupling parsing to HTTP or filesystem paths."""

    def __init__(
        self,
        session: AsyncSession,
        storage: StorageProvider,
        extractors: Sequence[DocumentExtractor] | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._repository = DocumentExtractionRepository(session)
        self._extractors = tuple(extractors or (PDFExtractor(), DOCXExtractor()))

    async def get(self, access: DocumentAccess) -> DocumentExtraction:
        extraction = await self._repository.get_by_document_id(access.document.id)
        if extraction is None:
            raise DomainError(status.HTTP_404_NOT_FOUND, "Document extraction not found")
        return extraction

    async def extract(self, access: DocumentAccess) -> DocumentExtraction:
        document = access.document
        extractor = self._select_extractor(document.mime_type)
        extraction = await self._repository.get_by_document_id(document.id)

        if (
            extraction is not None
            and extraction.status == ExtractionStatus.COMPLETED
            and extraction.source_sha256_hash == document.sha256_hash
        ):
            return extraction
        if extraction is not None and extraction.status in {
            ExtractionStatus.PENDING,
            ExtractionStatus.PROCESSING,
        }:
            raise DomainError(
                status.HTTP_409_CONFLICT,
                "Document extraction is already in progress",
            )

        try:
            if extraction is None:
                extraction = DocumentExtraction(
                    document_id=document.id,
                    extractor_type=extractor.extractor_type,
                    extractor_version=extractor.extractor_version,
                    status=ExtractionStatus.PENDING,
                    text_content="",
                    character_count=0,
                    page_count=None,
                    source_sha256_hash=document.sha256_hash,
                )
                await self._repository.create(extraction)
            else:
                self._reset_for_retry(extraction, extractor, document.sha256_hash)
                await self._repository.save(extraction)
            await self._session.commit()

            extraction.status = ExtractionStatus.PROCESSING
            await self._repository.save(extraction)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            LOGGER.error(
                "document_extraction_persistence_failed document_id=%s stage=prepare category=%s",
                document.id,
                type(exc).__name__,
            )
            raise DomainError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Unable to start document extraction",
            ) from exc

        try:
            with self._storage.open(document.storage_key) as source:
                extracted = await extractor.extract(source)
            text_content = render_extracted_text(extracted)

            extraction.status = ExtractionStatus.COMPLETED
            extraction.text_content = text_content
            extraction.character_count = len(text_content)
            extraction.page_count = extracted.page_count
            extraction.source_sha256_hash = document.sha256_hash
            extraction.extracted_at = utc_now()
            extraction.error_code = None
            extraction.error_message = None
            await self._repository.save(extraction)
            await self._session.commit()
            await self._session.refresh(extraction)
            LOGGER.info(
                "document_extraction_succeeded document_id=%s extractor=%s character_count=%s page_count=%s",
                document.id,
                extractor.extractor_type,
                extraction.character_count,
                extraction.page_count,
            )
            return extraction
        except ExtractionError as exc:
            await self._record_failure(
                document.id,
                exc.code,
                exc.safe_message,
                type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
            )
            raise DomainError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Document text extraction failed",
            ) from exc
        except (InvalidStorageKeyError, StorageError) as exc:
            await self._record_failure(
                document.id,
                "SOURCE_UNAVAILABLE",
                "The original document is unavailable",
                type(exc).__name__,
            )
            raise DomainError(status.HTTP_404_NOT_FOUND, "Document file not found") from exc
        except DomainError:
            raise
        except Exception as exc:
            await self._record_failure(
                document.id,
                "EXTRACTION_ERROR",
                "The document could not be extracted",
                type(exc).__name__,
            )
            raise DomainError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Unable to complete document extraction",
            ) from exc

    def _select_extractor(self, media_type: str) -> DocumentExtractor:
        extractor = next(
            (candidate for candidate in self._extractors if candidate.supports(media_type)),
            None,
        )
        if extractor is None:
            raise DomainError(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "Document type does not support text extraction",
            )
        return extractor

    @staticmethod
    def _reset_for_retry(
        extraction: DocumentExtraction,
        extractor: DocumentExtractor,
        source_sha256_hash: str,
    ) -> None:
        extraction.extractor_type = extractor.extractor_type
        extraction.extractor_version = extractor.extractor_version
        extraction.status = ExtractionStatus.PENDING
        extraction.text_content = ""
        extraction.character_count = 0
        extraction.page_count = None
        extraction.source_sha256_hash = source_sha256_hash
        extraction.extracted_at = None
        extraction.error_code = None
        extraction.error_message = None

    async def _record_failure(
        self,
        document_id: UUID,
        error_code: str,
        error_message: str,
        category: str,
    ) -> None:
        await self._session.rollback()
        try:
            extraction = await self._repository.get_by_document_id(document_id)
            if extraction is not None:
                extraction.status = ExtractionStatus.FAILED
                extraction.text_content = ""
                extraction.character_count = 0
                extraction.page_count = None
                extraction.extracted_at = None
                extraction.error_code = error_code
                extraction.error_message = error_message
                await self._repository.save(extraction)
                await self._session.commit()
        except Exception as persistence_error:
            await self._session.rollback()
            LOGGER.error(
                "document_extraction_failure_persistence_failed document_id=%s category=%s",
                document_id,
                type(persistence_error).__name__,
            )
        LOGGER.error(
            "document_extraction_failed document_id=%s error_code=%s category=%s",
            document_id,
            error_code,
            category,
        )
