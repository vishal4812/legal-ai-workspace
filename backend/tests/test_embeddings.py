from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from app.ai.embeddings.base import EmbeddingError
from app.ai.embeddings.local import LocalEmbeddingProvider


class FakeModel:
    def __init__(self, vectors):
        self.vectors = vectors

    def passage_embed(self, _texts, **_kwargs):
        return iter(self.vectors)

    def query_embed(self, _text, **_kwargs):
        return iter(self.vectors)


async def test_empty_batch_does_not_load_model(tmp_path: Path) -> None:
    provider = LocalEmbeddingProvider("unused", 3, tmp_path, 2)
    assert await provider.embed_texts([]) == []
    assert provider._model is None


async def test_one_multiple_and_query_embeddings_validate_dimension(tmp_path: Path) -> None:
    provider = LocalEmbeddingProvider("test", 3, tmp_path, 2)
    provider._model = FakeModel([np.array([1, 2, 3]), np.array([4, 5, 6])])
    assert await provider.embed_texts(["one", "two"]) == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    provider._model = FakeModel([np.array([7, 8, 9])])
    assert await provider.embed_query("query") == [7.0, 8.0, 9.0]


@pytest.mark.parametrize(
    ("vectors", "code"),
    [
        ([np.array([1, 2])], "EMBEDDING_DIMENSION_MISMATCH"),
        ([np.array([1, float("nan"), 3])], "EMBEDDING_INVALID_VECTOR"),
        ([np.array([1, float("inf"), 3])], "EMBEDDING_INVALID_VECTOR"),
        ([], "EMBEDDING_RESULT_COUNT_MISMATCH"),
    ],
)
async def test_malformed_embeddings_fail_safely(tmp_path: Path, vectors, code: str) -> None:
    provider = LocalEmbeddingProvider("test", 3, tmp_path, 2)
    provider._model = FakeModel(vectors)
    with pytest.raises(EmbeddingError) as raised:
        await provider.embed_texts(["text"])
    assert raised.value.code == code


async def test_invalid_text_is_rejected(tmp_path: Path) -> None:
    provider = LocalEmbeddingProvider("test", 3, tmp_path, 2)
    with pytest.raises(EmbeddingError, match="non-empty"):
        await provider.embed_texts([""])
    with pytest.raises(EmbeddingError, match="must not be empty"):
        await provider.embed_query("  ")


async def test_configured_local_model_loads_and_returns_finite_512_vectors(
    tmp_path: Path,
) -> None:
    cache_path = Path(os.getenv("EMBEDDING_CACHE_PATH", str(tmp_path)))
    provider = LocalEmbeddingProvider(
        "jinaai/jina-embeddings-v2-small-en", 512, cache_path, 2
    )
    vectors = await provider.embed_texts(["termination clause", "invoice payment"])
    query = await provider.embed_query("contract termination")
    assert len(vectors) == 2
    assert all(len(vector) == 512 for vector in [*vectors, query])
    assert np.isfinite(np.asarray([*vectors, query])).all()
    assert vectors == await provider.embed_texts(["termination clause", "invoice payment"])
