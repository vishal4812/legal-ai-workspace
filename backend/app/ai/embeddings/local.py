from __future__ import annotations

import asyncio
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.ai.embeddings.base import EmbeddingError, EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    """Lazy CPU-only FastEmbed provider with bounded local inference."""

    def __init__(
        self,
        model_name: str,
        expected_dimension: int,
        cache_path: Path,
        batch_size: int,
        max_concurrency: int = 1,
    ) -> None:
        self._model_name = model_name
        self._dimension = expected_dimension
        self._cache_path = cache_path
        self._batch_size = batch_size
        self._model: Any | None = None
        self._load_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingError(
                "EMBEDDING_INVALID_INPUT",
                "Embedding input must contain non-empty text",
            )
        model = await self._get_model()
        async with self._semaphore:
            try:
                raw = await asyncio.to_thread(
                    lambda: list(
                        model.passage_embed(texts, batch_size=self._batch_size, parallel=None)
                    )
                )
            except Exception as exc:
                raise EmbeddingError(
                    "EMBEDDING_MODEL_UNAVAILABLE",
                    "The local embedding model is unavailable",
                ) from exc
        return self._validate(raw, len(texts))

    async def embed_query(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError(
                "EMBEDDING_INVALID_INPUT", "Search query must not be empty"
            )
        model = await self._get_model()
        async with self._semaphore:
            try:
                raw = await asyncio.to_thread(lambda: list(model.query_embed(text)))
            except Exception as exc:
                raise EmbeddingError(
                    "EMBEDDING_MODEL_UNAVAILABLE",
                    "The local embedding model is unavailable",
                ) from exc
        vectors = self._validate(raw, 1)
        return vectors[0]

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from fastembed import TextEmbedding

                supported = next(
                    (
                        item
                        for item in TextEmbedding.list_supported_models()
                        if item.get("model") == self._model_name
                    ),
                    None,
                )
                discovered_dimension = supported.get("dim") if supported else None
                if discovered_dimension != self._dimension:
                    raise EmbeddingError(
                        "EMBEDDING_DIMENSION_MISMATCH",
                        "The embedding model dimension does not match configuration",
                    )
                self._cache_path.mkdir(parents=True, exist_ok=True)
                self._model = await asyncio.to_thread(
                    TextEmbedding,
                    model_name=self._model_name,
                    cache_dir=str(self._cache_path),
                    lazy_load=True,
                    cuda=False,
                )
            except EmbeddingError:
                raise
            except Exception as exc:
                raise EmbeddingError(
                    "EMBEDDING_MODEL_UNAVAILABLE",
                    "The local embedding model is unavailable",
                ) from exc
        return self._model

    def _validate(self, vectors: Iterable[Any], expected_count: int) -> list[list[float]]:
        normalized: list[list[float]] = []
        try:
            for vector in vectors:
                values = [float(value) for value in vector]
                if len(values) != self._dimension:
                    raise EmbeddingError(
                        "EMBEDDING_DIMENSION_MISMATCH",
                        "The embedding model dimension does not match configuration",
                    )
                if not all(math.isfinite(value) for value in values):
                    raise EmbeddingError(
                        "EMBEDDING_INVALID_VECTOR",
                        "The local embedding model returned an invalid vector",
                    )
                normalized.append(values)
        except EmbeddingError:
            raise
        except (TypeError, ValueError, OverflowError) as exc:
            raise EmbeddingError(
                "EMBEDDING_INVALID_VECTOR",
                "The local embedding model returned an invalid vector",
            ) from exc
        if len(normalized) != expected_count:
            raise EmbeddingError(
                "EMBEDDING_RESULT_COUNT_MISMATCH",
                "The local embedding model returned an unexpected result count",
            )
        return normalized
