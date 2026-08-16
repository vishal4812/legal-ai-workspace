from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.database import DatabaseSession
from app.documents.chunking.deterministic import DeterministicLegalChunker
from app.models.workspace_member import WorkspaceRole
from app.schemas.indexing import DocumentIndexResponse
from app.security.authorization import (
    CaseAccess,
    DocumentAccessDependency,
    require_case_roles,
)
from app.services.indexing import DocumentIndexingService

router = APIRouter()

ERROR_RESPONSES = {
    403: {"description": "Insufficient workspace permissions"},
    404: {"description": "Workspace, case, document, or index not found"},
    409: {"description": "Extraction unavailable or indexing already in progress"},
    503: {"description": "Local embeddings or vector index unavailable"},
}


def _service(request: Request, session: DatabaseSession) -> DocumentIndexingService:
    settings = request.app.state.settings
    return DocumentIndexingService(
        session,
        DeterministicLegalChunker(
            settings.chunk_size,
            settings.chunk_overlap,
            settings.chunk_min_size,
        ),
        request.app.state.embedding_provider,
        request.app.state.vector_store,
        settings.embedding_batch_size,
    )


@router.post(
    "/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/index",
    response_model=DocumentIndexResponse,
    responses=ERROR_RESPONSES,
    summary="Index an authorized completed document extraction",
)
async def index_document(
    request: Request,
    session: DatabaseSession,
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
) -> DocumentIndexResponse:
    result = await _service(request, session).index(access)
    return DocumentIndexResponse.model_validate(result)


@router.get(
    "/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/index",
    response_model=DocumentIndexResponse,
    responses=ERROR_RESPONSES,
    summary="Get an authorized document indexing status",
)
async def get_document_index(
    request: Request,
    session: DatabaseSession,
    access: DocumentAccessDependency,
) -> DocumentIndexResponse:
    result = await _service(request, session).get(access)
    return DocumentIndexResponse.model_validate(result)
