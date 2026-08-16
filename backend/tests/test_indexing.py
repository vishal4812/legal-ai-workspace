from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk
from app.models.document_extraction import DocumentExtraction, ExtractionStatus
from app.models.document_index import DocumentIndex, IndexingStatus
from app.vector.base import VectorStoreError
from tests.phase3_helpers import add_member, create_account
from tests.phase5_helpers import (
    DOCX_MIME,
    create_document_context,
    make_docx,
    make_pdf,
    make_scanned_pdf,
)
from tests.phase7_helpers import (
    DeterministicTestEmbeddingProvider,
    FailingVectorStore,
    configure_phase7,
    extraction_url,
    indexing_urls,
    search_url,
)


async def extracted_context(client: AsyncClient, email: str, *, content: bytes | None = None):
    context = await create_document_context(client, email, content=content)
    _, workspace, legal_case, document, headers, _ = context
    response = await client.post(extraction_url(workspace, legal_case, document), headers=headers)
    assert response.status_code == 200, response.text
    return context


async def test_success_persists_exact_chunks_metadata_vectors_and_is_idempotent(
    client: AsyncClient,
    session: AsyncSession,
    application,
) -> None:
    embeddings, vectors = configure_phase7(application)
    original = make_pdf(
        *("Termination clause. Agreement may terminate after written notice." for _ in range(6)),
        *("Payment clause. Each invoice is payable within thirty days." for _ in range(6)),
    )
    _, workspace, legal_case, document, headers, _ = await extracted_context(
        client, "index-success@example.com", content=original
    )
    trigger_url, get_url = indexing_urls(workspace, legal_case, document)

    response = await client.post(trigger_url, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "COMPLETED"
    assert result["embedding_provider"] == "local-test"
    assert result["embedding_model"] == "deterministic-test-model"
    assert result["embedding_dimension"] == 4
    assert result["indexed_chunk_count"] > 1
    assert result["qdrant_collection"] == "test_chunks"
    assert (await client.get(get_url, headers=headers)).json() == result

    chunks = list(
        await session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == UUID(document["id"]))
            .order_by(DocumentChunk.chunk_index)
        )
    )
    assert len(chunks) == result["indexed_chunk_count"]
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(
        chunk.content_hash == hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
        for chunk in chunks
    )
    assert all(chunk.character_count == len(chunk.content) for chunk in chunks)
    assert all(chunk.chunk_metadata["workspace_id"] == workspace["id"] for chunk in chunks)
    assert any(chunk.page_start == 1 for chunk in chunks)
    assert any(chunk.page_end == 12 for chunk in chunks)
    assert await vectors.count_document_points(UUID(document["id"])) == len(chunks)

    first_ids = [chunk.id for chunk in chunks]
    calls = embeddings.calls
    repeated = await client.post(trigger_url, headers=headers)
    assert repeated.status_code == 200
    assert repeated.json() == result
    assert embeddings.calls == calls
    assert list(
        await session.scalars(
            select(DocumentChunk.id)
            .where(DocumentChunk.document_id == UUID(document["id"]))
            .order_by(DocumentChunk.chunk_index)
        )
    ) == first_ids
    assert int(await session.scalar(select(func.count()).select_from(DocumentIndex)) or 0) == 1


async def test_missing_incomplete_and_stale_extractions_are_rejected(
    client: AsyncClient, session: AsyncSession, application
) -> None:
    configure_phase7(application)
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client, "index-preconditions@example.com"
    )
    trigger_url, _ = indexing_urls(workspace, legal_case, document)
    missing = await client.post(trigger_url, headers=headers)
    assert missing.status_code == 409

    await client.post(extraction_url(workspace, legal_case, document), headers=headers)
    extraction = await session.scalar(
        select(DocumentExtraction).where(DocumentExtraction.document_id == UUID(document["id"]))
    )
    assert extraction is not None
    extraction.status = ExtractionStatus.FAILED
    await session.commit()
    assert (await client.post(trigger_url, headers=headers)).status_code == 409

    extraction.status = ExtractionStatus.COMPLETED
    extraction.source_sha256_hash = "0" * 64
    await session.commit()
    stale = await client.post(trigger_url, headers=headers)
    assert stale.status_code == 409
    assert "retained original" in stale.json()["detail"]


async def test_processing_conflict(
    client: AsyncClient, session: AsyncSession, application
) -> None:
    configure_phase7(application)
    _, workspace, legal_case, document, headers, _ = await extracted_context(
        client, "index-processing@example.com"
    )
    extraction = await session.scalar(
        select(DocumentExtraction).where(DocumentExtraction.document_id == UUID(document["id"]))
    )
    assert extraction is not None
    session.add(
        DocumentIndex(
            document_id=UUID(document["id"]),
            status=IndexingStatus.PROCESSING,
            embedding_provider="local-test",
            embedding_model="deterministic-test-model",
            embedding_dimension=4,
            indexed_chunk_count=0,
            source_extraction_sha256=hashlib.sha256(extraction.text_content.encode()).hexdigest(),
            qdrant_collection="test_chunks",
        )
    )
    await session.commit()
    trigger_url, _ = indexing_urls(workspace, legal_case, document)
    response = await client.post(trigger_url, headers=headers)
    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


async def test_qdrant_failure_persists_safe_failure_and_retry_reuses_row(
    client: AsyncClient, session: AsyncSession, application
) -> None:
    store = FailingVectorStore(fail_times=1)
    configure_phase7(application, vectors=store)
    _, workspace, legal_case, document, headers, _ = await extracted_context(
        client,
        "index-retry@example.com",
        content=make_pdf("Termination rights and written notice. " * 20),
    )
    trigger_url, get_url = indexing_urls(workspace, legal_case, document)
    failed = await client.post(trigger_url, headers=headers)
    assert failed.status_code == 503
    assert failed.json() == {"detail": "Document indexing failed"}
    persisted = (await client.get(get_url, headers=headers)).json()
    assert persisted["status"] == "FAILED"
    assert persisted["error_code"] == "QDRANT_INDEXING_FAILED"
    assert "path" not in persisted["error_message"].casefold()
    failed_id = persisted["id"]

    retried = await client.post(trigger_url, headers=headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "COMPLETED"
    assert retried.json()["id"] == failed_id
    assert int(await session.scalar(select(func.count()).select_from(DocumentIndex)) or 0) == 1


async def test_embedding_failure_is_bounded_and_persisted(
    client: AsyncClient, application
) -> None:
    configure_phase7(
        application, embeddings=DeterministicTestEmbeddingProvider(fail=True)
    )
    _, workspace, legal_case, document, headers, _ = await extracted_context(
        client, "embedding-failure@example.com"
    )
    trigger_url, get_url = indexing_urls(workspace, legal_case, document)
    response = await client.post(trigger_url, headers=headers)
    assert response.status_code == 503
    persisted = (await client.get(get_url, headers=headers)).json()
    assert persisted["status"] == "FAILED"
    assert persisted["error_code"] == "EMBEDDING_MODEL_UNAVAILABLE"
    assert persisted["error_message"] == "The local embedding model is unavailable"


async def test_changed_extraction_reindexes_and_removes_stale_points(
    client: AsyncClient, session: AsyncSession, application
) -> None:
    _, store = configure_phase7(application)
    _, workspace, legal_case, document, headers, _ = await extracted_context(
        client,
        "reindex@example.com",
        content=make_pdf("Termination section with notice. " * 15),
    )
    trigger_url, _ = indexing_urls(workspace, legal_case, document)
    first = (await client.post(trigger_url, headers=headers)).json()
    original_chunk_ids = set(
        await session.scalars(
            select(DocumentChunk.id).where(DocumentChunk.document_id == UUID(document["id"]))
        )
    )
    extraction = await session.scalar(
        select(DocumentExtraction).where(DocumentExtraction.document_id == UUID(document["id"]))
    )
    assert extraction is not None
    extraction.text_content = "[Page 1]\n\nConfidential evidence is protected. " * 12
    extraction.character_count = len(extraction.text_content)
    await session.commit()

    second = await client.post(trigger_url, headers=headers)
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert second.json()["source_extraction_sha256"] != first["source_extraction_sha256"]
    current_ids = set(
        await session.scalars(
            select(DocumentChunk.id).where(DocumentChunk.document_id == UUID(document["id"]))
        )
    )
    assert current_ids.isdisjoint(original_chunk_ids)
    assert await store.count_document_points(UUID(document["id"])) == len(current_ids)


@pytest.mark.parametrize(
    ("role", "post_status"),
    [("OWNER", 200), ("ADMIN", 200), ("MEMBER", 200), ("VIEWER", 403)],
)
async def test_index_authorization_matrix(
    client: AsyncClient, application, role: str, post_status: int
) -> None:
    configure_phase7(application)
    _, workspace, legal_case, document, owner_headers, _ = await extracted_context(
        client, f"index-role-owner-{role.casefold()}@example.com"
    )
    if role == "OWNER":
        actor_headers = owner_headers
    else:
        actor, actor_headers = await create_account(
            client, f"index-role-{role.casefold()}@example.com"
        )
        await add_member(client, workspace["id"], owner_headers, actor["email"], role)
    trigger_url, get_url = indexing_urls(workspace, legal_case, document)
    if role == "VIEWER":
        assert (await client.post(trigger_url, headers=owner_headers)).status_code == 200
    response = await client.post(trigger_url, headers=actor_headers)
    assert response.status_code == post_status
    viewed = await client.get(get_url, headers=actor_headers)
    assert viewed.status_code == 200
    assert viewed.json()["status"] == "COMPLETED"


async def test_semantic_search_ranking_case_filter_viewer_and_tenant_isolation(
    client: AsyncClient, application
) -> None:
    configure_phase7(application)
    _, workspace_a, case_a, document_a, headers_a, _ = await extracted_context(
        client,
        "search-a@example.com",
        content=make_pdf(
            *("Termination termination termination written notice clause." for _ in range(7)),
            *("Payment invoice is due within thirty days." for _ in range(7)),
        ),
    )
    assert (
        await client.post(indexing_urls(workspace_a, case_a, document_a)[0], headers=headers_a)
    ).status_code == 200
    _, workspace_b, case_b, document_b, headers_b, _ = await extracted_context(
        client,
        "search-b@example.com",
        content=make_pdf("Confidential evidence for another tenant. " * 12),
    )
    assert (
        await client.post(indexing_urls(workspace_b, case_b, document_b)[0], headers=headers_b)
    ).status_code == 200

    actor, viewer_headers = await create_account(client, "search-viewer@example.com")
    await add_member(client, workspace_a["id"], headers_a, actor["email"], "VIEWER")
    response = await client.post(
        search_url(workspace_a["id"]),
        headers=viewer_headers,
        json={"query": "termination clause", "case_id": case_a["id"], "top_k": 3},
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results
    assert all(result["document_id"] == document_a["id"] for result in results)
    assert results[0]["score"] >= results[-1]["score"]
    assert "Termination" in results[0]["content"]
    assert all(result["case_id"] == case_a["id"] for result in results)
    assert (await client.post(indexing_urls(workspace_a, case_a, document_a)[0], headers=viewer_headers)).status_code == 403

    assert (
        await client.post(
            search_url(workspace_b["id"]),
            headers=viewer_headers,
            json={"query": "confidential evidence"},
        )
    ).status_code == 404
    mismatch = await client.post(
        search_url(workspace_a["id"]),
        headers=viewer_headers,
        json={"query": "evidence", "case_id": case_b["id"]},
    )
    assert mismatch.status_code == 404
    assert (
        await client.get(
            f"/api/v1/workspaces/{workspace_a['id']}/chunks/{uuid4()}",
            headers=viewer_headers,
        )
    ).status_code == 404


async def test_nested_index_workspace_case_document_mismatches_are_404(
    client: AsyncClient, application
) -> None:
    configure_phase7(application)
    _, workspace_a, case_a, document_a, headers_a, _ = await extracted_context(
        client, "mismatch-a@example.com"
    )
    _, workspace_b, case_b, document_b, headers_b, _ = await extracted_context(
        client, "mismatch-b@example.com"
    )
    del headers_b
    urls = [
        indexing_urls(workspace_b, case_b, document_b)[0],
        f"/api/v1/workspaces/{workspace_a['id']}/cases/{case_b['id']}/documents/{document_b['id']}/index",
        f"/api/v1/workspaces/{workspace_a['id']}/cases/{case_a['id']}/documents/{document_b['id']}/index",
    ]
    for url in urls:
        assert (await client.post(url, headers=headers_a)).status_code == 404
        assert (await client.get(url, headers=headers_a)).status_code == 404


async def test_search_qdrant_unavailable_is_safe(client: AsyncClient, application) -> None:
    class UnavailableStore(FailingVectorStore):
        async def ensure_collection(self, dimension: int) -> None:
            raise VectorStoreError("QDRANT_UNAVAILABLE", "The vector index is unavailable")

    configure_phase7(application, vectors=UnavailableStore())
    _, workspace, _, _, headers, _ = await create_document_context(
        client, "search-unavailable@example.com"
    )
    response = await client.post(
        search_url(workspace["id"]), headers=headers, json={"query": "termination"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "The vector index is unavailable"}
    assert "qdrant" not in response.text.casefold()


async def test_search_empty_results_and_request_bounds(client: AsyncClient, application) -> None:
    configure_phase7(application)
    _, workspace, _, _, headers, _ = await create_document_context(
        client, "search-empty@example.com"
    )
    empty = await client.post(
        search_url(workspace["id"]), headers=headers, json={"query": "termination"}
    )
    assert empty.status_code == 200
    assert empty.json() == {"results": []}
    for payload in (
        {"query": "   "},
        {"query": "valid", "top_k": 0},
        {"query": "valid", "top_k": 51},
    ):
        assert (
            await client.post(search_url(workspace["id"]), headers=headers, json=payload)
        ).status_code == 422


@pytest.mark.parametrize(
    ("filename", "mime_type", "content", "expected_method"),
    [
        (
            "scanned.pdf",
            "application/pdf",
            make_scanned_pdf("SCANNED TERMINATION CLAUSE REQUIRES WRITTEN NOTICE"),
            "ocr",
        ),
        (
            "paragraphs.docx",
            DOCX_MIME,
            make_docx(
                heading="Termination",
                paragraphs=("Written notice is required.", "Payment is due in thirty days."),
            ),
            "direct_text",
        ),
        (
            "table.docx",
            DOCX_MIME,
            make_docx(table=(("Clause", "Period"), ("Notice", "90 days"))),
            "direct_text",
        ),
    ],
)
async def test_real_ocr_and_docx_extractions_flow_through_chunking_and_vectors(
    client: AsyncClient,
    session: AsyncSession,
    application,
    filename: str,
    mime_type: str,
    content: bytes,
    expected_method: str,
) -> None:
    configure_phase7(application)
    _, workspace, legal_case, document, headers, original = await create_document_context(
        client,
        f"pipeline-{filename.replace('.', '-')}@example.com",
        filename=filename,
        content=content,
        mime_type=mime_type,
    )
    extracted = await client.post(
        extraction_url(workspace, legal_case, document), headers=headers
    )
    assert extracted.status_code == 200, extracted.text
    assert extracted.json()["parser_metadata"]["method"] == expected_method
    indexed = await client.post(
        indexing_urls(workspace, legal_case, document)[0], headers=headers
    )
    assert indexed.status_code == 200, indexed.text
    assert indexed.json()["status"] == "COMPLETED"
    chunks = list(
        await session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == UUID(document["id"]))
        )
    )
    assert chunks
    assert all(chunk.chunk_metadata["extraction_method"] == expected_method for chunk in chunks)
    assert hashlib.sha256(original).hexdigest() == document["sha256_hash"]
