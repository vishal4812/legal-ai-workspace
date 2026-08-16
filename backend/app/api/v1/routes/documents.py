from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.database import DatabaseSession
from app.documents.extractors.docx import DOCXExtractor
from app.documents.extractors.pdf import PDFExtractor
from app.models.workspace_member import WorkspaceRole
from app.schemas.documents import (
    DocumentExtractionResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.security.authorization import (
    CaseAccess,
    CaseAccessDependency,
    DocumentAccessDependency,
    require_case_roles,
)
from app.services.documents import DocumentService
from app.services.extractions import DocumentExtractionService
from app.storage.dependencies import DocumentStorage

router = APIRouter()

ERROR_RESPONSES = {
    401: {"description": "Authentication required"},
    403: {"description": "Insufficient workspace role"},
    404: {"description": "Workspace, case, or document not found"},
}
UPLOAD_ERROR_RESPONSES = {
    **ERROR_RESPONSES,
    413: {"description": "File exceeds configured maximum size"},
    415: {"description": "Unsupported or invalid document type"},
    422: {"description": "Invalid upload metadata or empty file"},
}


def iter_file(content: BinaryIO, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with content:
        while chunk := content.read(chunk_size):
            yield chunk


def content_disposition(filename: str) -> str:
    fallback = filename.encode("ascii", "replace").decode("ascii")
    fallback = fallback.replace("\\", "_").replace('"', "_") or "document"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


@router.post(
    "/workspaces/{workspace_id}/cases/{case_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses=UPLOAD_ERROR_RESPONSES,
    summary="Upload a private PDF or DOCX document",
)
async def upload_document(
    request: Request,
    session: DatabaseSession,
    storage: DocumentStorage,
    access: Annotated[
        CaseAccess,
        Depends(
            require_case_roles(
                WorkspaceRole.OWNER,
                WorkspaceRole.ADMIN,
                WorkspaceRole.MEMBER,
            )
        ),
    ],
    file: Annotated[
        UploadFile,
        File(description="Original PDF or DOCX binary; maximum size is server-configured"),
    ],
) -> DocumentUploadResponse:
    document = await DocumentService(
        session,
        storage,
        request.app.state.settings.document_max_size_bytes,
    ).upload(access, file)
    return DocumentUploadResponse.model_validate(document)


@router.get(
    "/workspaces/{workspace_id}/cases/{case_id}/documents",
    response_model=list[DocumentResponse],
    responses=ERROR_RESPONSES,
    summary="List retained documents for a case",
)
async def list_documents(
    request: Request,
    session: DatabaseSession,
    storage: DocumentStorage,
    access: CaseAccessDependency,
) -> list[DocumentResponse]:
    documents = await DocumentService(
        session,
        storage,
        request.app.state.settings.document_max_size_bytes,
    ).list_for_case(access.case.id)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get(
    "/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}",
    response_model=DocumentResponse,
    responses=ERROR_RESPONSES,
    summary="Get retained document metadata",
)
async def get_document(access: DocumentAccessDependency) -> DocumentResponse:
    return DocumentResponse.model_validate(access.document)


@router.post(
    "/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/extract",
    response_model=DocumentExtractionResponse,
    responses={
        **ERROR_RESPONSES,
        409: {"description": "Extraction is already pending or processing"},
        415: {"description": "Document type is not extractable"},
        422: {"description": "The document parser rejected the original"},
    },
    summary="Extract machine-readable text from an authorized document",
)
async def extract_document(
    request: Request,
    session: DatabaseSession,
    storage: DocumentStorage,
    access: DocumentAccessDependency,
    _case_access: Annotated[
        CaseAccess,
        Depends(
            require_case_roles(
                WorkspaceRole.OWNER,
                WorkspaceRole.ADMIN,
                WorkspaceRole.MEMBER,
            )
        ),
    ],
) -> DocumentExtractionResponse:
    settings = request.app.state.settings
    pdf_extractor = PDFExtractor(
        ocr_provider=request.app.state.ocr_provider,
        ocr_enabled=settings.ocr_enabled,
        ocr_language=settings.ocr_lang,
        ocr_dpi=settings.ocr_dpi,
        ocr_max_pages=settings.ocr_max_pages,
        ocr_timeout_seconds=settings.ocr_timeout_seconds,
        ocr_max_image_pixels=settings.ocr_max_image_pixels,
    )
    extraction = await DocumentExtractionService(
        session,
        storage,
        extractors=(pdf_extractor, DOCXExtractor()),
    ).extract(access)
    return DocumentExtractionResponse.model_validate(extraction)


@router.get(
    "/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/extraction",
    response_model=DocumentExtractionResponse,
    responses=ERROR_RESPONSES,
    summary="Get authorized extracted text and extraction metadata",
)
async def get_document_extraction(
    session: DatabaseSession,
    storage: DocumentStorage,
    access: DocumentAccessDependency,
) -> DocumentExtractionResponse:
    extraction = await DocumentExtractionService(session, storage).get(access)
    return DocumentExtractionResponse.model_validate(extraction)


@router.get(
    "/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/download",
    response_class=StreamingResponse,
    responses={
        **ERROR_RESPONSES,
        200: {
            "description": "Original document binary",
            "content": {
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
            },
        },
    },
    summary="Download an authorized retained original",
)
async def download_document(
    request: Request,
    session: DatabaseSession,
    storage: DocumentStorage,
    access: DocumentAccessDependency,
) -> StreamingResponse:
    artifact = DocumentService(
        session,
        storage,
        request.app.state.settings.document_max_size_bytes,
    ).open_download(access)
    return StreamingResponse(
        iter_file(artifact.content),
        media_type=artifact.mime_type,
        headers={
            "Content-Length": str(artifact.file_size),
            "Content-Disposition": content_disposition(artifact.filename),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}",
    response_model=DocumentResponse,
    responses=ERROR_RESPONSES,
    summary="Archive a document without deleting its retained original",
)
async def archive_document(
    request: Request,
    session: DatabaseSession,
    storage: DocumentStorage,
    access: DocumentAccessDependency,
    _case_access: Annotated[
        CaseAccess,
        Depends(
            require_case_roles(
                WorkspaceRole.OWNER,
                WorkspaceRole.ADMIN,
                WorkspaceRole.MEMBER,
            )
        ),
    ],
) -> DocumentResponse:
    document = await DocumentService(
        session,
        storage,
        request.app.state.settings.document_max_size_bytes,
    ).archive(access)
    return DocumentResponse.model_validate(document)
