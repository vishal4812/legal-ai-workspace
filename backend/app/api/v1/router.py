from fastapi import APIRouter

from app.api.v1.routes import analysis, auth, cases, chat, documents, workspaces
from app.schemas.health import ApiRootResponse

api_router = APIRouter()


@api_router.get("", response_model=ApiRootResponse, tags=["system"])
async def api_root() -> ApiRootResponse:
    return ApiRootResponse(name="LEGAL MASTER API", version="v1")


api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(cases.router, tags=["cases"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
