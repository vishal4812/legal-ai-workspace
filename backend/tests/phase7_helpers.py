from __future__ import annotations

import math
from collections import Counter
from uuid import UUID

from qdrant_client import QdrantClient

from app.ai.embeddings.base import EmbeddingError, EmbeddingProvider
from app.vector.base import VectorStoreError
from app.vector.qdrant import QdrantVectorStore
from tests.phase5_helpers import document_base


class DeterministicTestEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, fail: bool = False, malformed: bool = False) -> None:
        self.fail = fail
        self.malformed = malformed
        self.calls = 0

    @property
    def dimension(self) -> int:
        return 4

    @property
    def provider_name(self) -> str:
        return "local-test"

    @property
    def model_name(self) -> str:
        return "deterministic-test-model"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise EmbeddingError("EMBEDDING_MODEL_UNAVAILABLE", "The local embedding model is unavailable")
        vectors = [self._vector(text) for text in texts]
        if self.malformed and vectors:
            vectors[0] = [float("nan")] * 4
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        if self.fail:
            raise EmbeddingError("EMBEDDING_MODEL_UNAVAILABLE", "The local embedding model is unavailable")
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        words = Counter(word.strip(".,;:!?()[]").casefold() for word in text.split())
        values = [
            float(words["termination"] + words["terminate"] + 1),
            float(words["payment"] + words["invoice"] + 1),
            float(words["confidential"] + words["confidentiality"] + 1),
            float(words["evidence"] + words["court"] + 1),
        ]
        length = math.sqrt(sum(value * value for value in values))
        return [value / length for value in values]


class FailingVectorStore(QdrantVectorStore):
    def __init__(self, *, fail_times: int = 1) -> None:
        super().__init__(None, None, "test_chunks", 5, 8, client=QdrantClient(":memory:"))
        self.fail_times = fail_times

    async def replace_document_points(self, document_id, points):
        if self.fail_times:
            self.fail_times -= 1
            raise VectorStoreError("QDRANT_INDEXING_FAILED", "The document vector index could not be updated")
        await super().replace_document_points(document_id, points)


def configure_phase7(application, *, embeddings=None, vectors=None):
    embedding_provider = embeddings or DeterministicTestEmbeddingProvider()
    vector_store = vectors or QdrantVectorStore(
        None,
        None,
        "test_chunks",
        5,
        8,
        client=QdrantClient(":memory:"),
    )
    application.state.embedding_provider = embedding_provider
    application.state.vector_store = vector_store
    application.state.settings.embedding_batch_size = 8
    application.state.settings.chunk_size = 50
    application.state.settings.chunk_overlap = 10
    application.state.settings.chunk_min_size = 10
    return embedding_provider, vector_store


def indexing_urls(workspace: dict, legal_case: dict, document: dict) -> tuple[str, str]:
    url = f"{document_base(workspace, legal_case)}/{document['id']}/index"
    return url, url


def extraction_url(workspace: dict, legal_case: dict, document: dict) -> str:
    return f"{document_base(workspace, legal_case)}/{document['id']}/extract"


def search_url(workspace_id: str | UUID) -> str:
    return f"/api/v1/workspaces/{workspace_id}/search"
