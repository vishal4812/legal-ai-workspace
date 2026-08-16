from __future__ import annotations

import hashlib
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.repositories.documents import DocumentRepository
from app.security.authorization import CaseAccess, DocumentAccess
from app.services.errors import DomainError
from app.storage.base import StorageProvider
from app.storage.local import InvalidStorageKeyError, StorageError

LOGGER = logging.getLogger(__name__)
UPLOAD_CHUNK_SIZE = 1024 * 1024
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_TYPES = {".pdf": PDF_MIME, ".docx": DOCX_MIME}
MAX_FILENAME_CHARACTERS = 255
MAX_FILENAME_BYTES = 512


@dataclass(frozen=True)
class DownloadArtifact:
    content: BinaryIO
    filename: str
    mime_type: str
    file_size: int


def validate_filename(raw_filename: str | None) -> tuple[str, str]:
    if not raw_filename:
        raise DomainError(status.HTTP_422_UNPROCESSABLE_CONTENT, "A filename is required")
    normalized = unicodedata.normalize("NFC", raw_filename)
    if (
        normalized != raw_filename
        or len(normalized) > MAX_FILENAME_CHARACTERS
        or len(normalized.encode("utf-8")) > MAX_FILENAME_BYTES
        or normalized in {".", ".."}
        or "/" in normalized
        or "\\" in normalized
        or PurePath(normalized).is_absolute()
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise DomainError(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid filename")
    extension = PurePath(normalized).suffix.casefold()
    if extension not in ALLOWED_TYPES:
        raise DomainError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF and DOCX files are supported")
    return normalized, extension


def validate_mime_type(extension: str, mime_type: str | None) -> str:
    expected = ALLOWED_TYPES[extension]
    if mime_type != expected:
        raise DomainError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "File extension and media type do not match",
        )
    return expected


def validate_binary(staged_content: BinaryIO, extension: str) -> None:
    if extension == ".pdf":
        if staged_content.read(5) != b"%PDF-":
            raise DomainError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Invalid PDF file signature")
        return

    try:
        staged_content.seek(0)
        with ZipFile(staged_content) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise DomainError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Invalid DOCX package")
            content_type_info = archive.getinfo("[Content_Types].xml")
            if content_type_info.file_size > 1024 * 1024:
                raise DomainError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Invalid DOCX package")
            content_types = archive.read(content_type_info)
            expected_type = (
                b"application/vnd.openxmlformats-officedocument."
                b"wordprocessingml.document.main+xml"
            )
            if expected_type not in content_types:
                raise DomainError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Invalid DOCX package")
    except DomainError:
        raise
    except (BadZipFile, KeyError, OSError, RuntimeError) as exc:
        raise DomainError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Invalid DOCX file signature") from exc


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageProvider,
        max_size_bytes: int,
    ) -> None:
        self._session = session
        self._storage = storage
        self._max_size_bytes = max_size_bytes
        self._repository = DocumentRepository(session)

    async def upload(self, access: CaseAccess, upload: UploadFile) -> Document:
        filename, extension = validate_filename(upload.filename)
        mime_type = validate_mime_type(extension, upload.content_type)
        document_id = uuid4()
        workspace_id = access.workspace_access.workspace.id
        case_id = access.case.id
        user_id = access.workspace_access.user.id
        stored_filename = document_id.hex
        storage_key = (
            f"{workspace_id}/"
            f"{case_id}/{document_id}/{stored_filename}"
        )
        digest = hashlib.sha256()
        file_size = 0
        published = False

        try:
            staged = self._storage.stage()
        except StorageError as exc:
            raise DomainError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to store document") from exc

        try:
            while True:
                read_size = min(UPLOAD_CHUNK_SIZE, self._max_size_bytes - file_size + 1)
                chunk = await upload.read(read_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > self._max_size_bytes:
                    raise DomainError(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"File exceeds the {self._max_size_bytes}-byte upload limit",
                    )
                digest.update(chunk)
                staged.write(chunk)

            if file_size == 0:
                raise DomainError(status.HTTP_422_UNPROCESSABLE_CONTENT, "Uploaded file is empty")

            with staged.open() as staged_content:
                validate_binary(staged_content, extension)
            staged.commit(storage_key)
            published = True

            document = Document(
                id=document_id,
                case_id=case_id,
                created_by=user_id,
                original_filename=filename,
                stored_filename=stored_filename,
                mime_type=mime_type,
                file_size=file_size,
                sha256_hash=digest.hexdigest(),
                storage_key=storage_key,
                status=DocumentStatus.UPLOADED,
                is_active=True,
            )
            await self._repository.create(document)
            await self._session.commit()
            LOGGER.info(
                "document_upload_succeeded document_id=%s case_id=%s workspace_id=%s user_id=%s",
                document.id,
                document.case_id,
                workspace_id,
                user_id,
            )
            return document
        except DomainError:
            await self._session.rollback()
            if published:
                self._cleanup_published(storage_key)
            raise
        except StorageError as exc:
            await self._session.rollback()
            if published:
                self._cleanup_published(storage_key)
            raise DomainError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to store document") from exc
        except Exception:
            await self._session.rollback()
            if published:
                self._cleanup_published(storage_key)
            LOGGER.error(
                "document_upload_failed case_id=%s workspace_id=%s user_id=%s category=database",
                case_id,
                workspace_id,
                user_id,
            )
            raise DomainError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Unable to save document metadata",
            )
        finally:
            try:
                staged.discard()
            except StorageError:
                LOGGER.error(
                    "document_staging_cleanup_failed case_id=%s workspace_id=%s",
                    case_id,
                    workspace_id,
                )

    def _cleanup_published(self, storage_key: str) -> None:
        try:
            self._storage.delete(storage_key)
        except StorageError:
            LOGGER.error("document_orphan_cleanup_failed category=storage")

    async def list_for_case(self, case_id: UUID) -> list[Document]:
        return await self._repository.list_by_case(case_id)

    async def archive(self, access: DocumentAccess) -> Document:
        document = await self._repository.archive(access.document)
        await self._session.commit()
        await self._session.refresh(document)
        return document

    def open_download(self, access: DocumentAccess) -> DownloadArtifact:
        document = access.document
        try:
            content = self._storage.open(document.storage_key)
        except (InvalidStorageKeyError, StorageError):
            raise DomainError(status.HTTP_404_NOT_FOUND, "Document file not found")
        try:
            actual_size = self._storage.size(document.storage_key)
        except (InvalidStorageKeyError, StorageError):
            content.close()
            raise DomainError(status.HTTP_404_NOT_FOUND, "Document file not found")
        return DownloadArtifact(
            content=content,
            filename=document.original_filename,
            mime_type=document.mime_type,
            file_size=actual_size,
        )
