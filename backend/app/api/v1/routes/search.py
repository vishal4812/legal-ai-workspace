from __future__ import annotations

from fastapi import APIRouter, Request

from app.database import DatabaseSession
from app.schemas.indexing import (
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchResultResponse,
)
from app.security.authorization import WorkspaceAccessDependency
from app.services.search import VectorSearchService

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}/search",
    response_model=SemanticSearchResponse,
    responses={
        404: {"description": "Workspace or case not found"},
        503: {"description": "Local embeddings or vector search unavailable"},
    },
    summary="Return tenant-scoped semantic chunk matches without answer generation",
)
async def semantic_search(
    payload: SemanticSearchRequest,
    request: Request,
    session: DatabaseSession,
    access: WorkspaceAccessDependency,
) -> SemanticSearchResponse:
    results = await VectorSearchService(
        session,
        request.app.state.embedding_provider,
        request.app.state.vector_store,
    ).search(access, payload.query, payload.case_id, payload.top_k)
    return SemanticSearchResponse(
        results=[SemanticSearchResultResponse.model_validate(result) for result in results]
    )
