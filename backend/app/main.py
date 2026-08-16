from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.api.v1.routes.health import router as health_router
from app.ai.embeddings.local import LocalEmbeddingProvider
from app.config import Settings, get_settings
from app.database import Database
from app.logging import configure_logging
from app.documents.ocr.tesseract import TesseractOCRProvider
from app.services.errors import DomainError
from app.storage.local import LocalStorageProvider
from app.vector.qdrant import QdrantVectorStore


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.settings = resolved_settings
        application.state.database = Database(resolved_settings.database_url)
        try:
            yield
        finally:
            await application.state.vector_store.close()
            await application.state.database.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.document_storage = LocalStorageProvider(
        resolved_settings.document_storage_path
    )
    application.state.ocr_provider = TesseractOCRProvider(
        resolved_settings.ocr_lang,
        resolved_settings.ocr_max_concurrency,
    )
    application.state.embedding_provider = LocalEmbeddingProvider(
        resolved_settings.embedding_model,
        resolved_settings.embedding_dimension,
        resolved_settings.embedding_cache_path,
        resolved_settings.embedding_batch_size,
        resolved_settings.embedding_max_concurrency,
    )
    application.state.vector_store = QdrantVectorStore(
        resolved_settings.qdrant_url,
        (
            resolved_settings.qdrant_api_key.get_secret_value()
            if resolved_settings.qdrant_api_key
            else None
        ),
        resolved_settings.qdrant_collection_name,
        resolved_settings.qdrant_timeout_seconds,
        resolved_settings.qdrant_upsert_batch_size,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @application.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    application.include_router(health_router)
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
