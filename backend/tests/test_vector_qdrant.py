from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient, models

from app.vector.base import VectorPoint, VectorStoreError
from app.vector.qdrant import QdrantVectorStore


def store(client: QdrantClient, name: str = "chunks") -> QdrantVectorStore:
    return QdrantVectorStore(None, None, name, 5, 2, client=client)


async def test_collection_creation_existing_validation_and_payload_indexes() -> None:
    client = QdrantClient(":memory:")
    adapter = store(client)
    with patch.object(
        client, "create_payload_index", wraps=client.create_payload_index
    ) as create_payload_index:
        await adapter.ensure_collection(4)
        await adapter.ensure_collection(4)
    info = client.get_collection("chunks")
    assert isinstance(info.config.params.vectors, models.VectorParams)
    assert info.config.params.vectors.size == 4
    assert info.config.params.vectors.distance == models.Distance.COSINE
    assert {call.kwargs["field_name"] for call in create_payload_index.call_args_list} == {
        "workspace_id",
        "case_id",
        "document_id",
    }


@pytest.mark.parametrize(
    ("size", "distance", "code"),
    [
        (3, models.Distance.COSINE, "QDRANT_DIMENSION_MISMATCH"),
        (4, models.Distance.DOT, "QDRANT_DISTANCE_MISMATCH"),
    ],
)
async def test_incompatible_collection_is_not_recreated(size, distance, code: str) -> None:
    client = QdrantClient(":memory:")
    client.create_collection(
        "chunks", vectors_config=models.VectorParams(size=size, distance=distance)
    )
    with pytest.raises(VectorStoreError) as raised:
        await store(client).ensure_collection(4)
    assert raised.value.code == code
    assert client.collection_exists("chunks")


async def test_upsert_replace_count_search_and_tenant_case_filters() -> None:
    client = QdrantClient(":memory:")
    adapter = store(client)
    await adapter.ensure_collection(4)
    workspace_a, workspace_b = uuid4(), uuid4()
    case_a, case_b = uuid4(), uuid4()
    document_a, document_b = uuid4(), uuid4()
    chunk_a, chunk_b = uuid4(), uuid4()
    await adapter.replace_document_points(
        document_a,
        [
            VectorPoint(
                chunk_a,
                [1.0, 0.0, 0.0, 0.0],
                {
                    "workspace_id": str(workspace_a),
                    "case_id": str(case_a),
                    "document_id": str(document_a),
                },
            )
        ],
    )
    await adapter.replace_document_points(
        document_b,
        [
            VectorPoint(
                chunk_b,
                [1.0, 0.0, 0.0, 0.0],
                {
                    "workspace_id": str(workspace_b),
                    "case_id": str(case_b),
                    "document_id": str(document_b),
                },
            )
        ],
    )
    assert await adapter.count_document_points(document_a) == 1
    hits = await adapter.search([1.0, 0.0, 0.0, 0.0], workspace_a, case_a, 5)
    assert [hit.id for hit in hits] == [chunk_a]

    replacement = uuid4()
    await adapter.replace_document_points(
        document_a,
        [
            VectorPoint(
                replacement,
                [0.0, 1.0, 0.0, 0.0],
                {
                    "workspace_id": str(workspace_a),
                    "case_id": str(case_a),
                    "document_id": str(document_a),
                },
            )
        ],
    )
    assert await adapter.count_document_points(document_a) == 1
    assert [
        hit.id
        for hit in await adapter.search([0.0, 1.0, 0.0, 0.0], workspace_a, None, 5)
    ] == [replacement]
