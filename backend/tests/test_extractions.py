from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extractors.base import ExtractionError
from app.documents.extractors.pdf import PDFExtractor
from app.models.document import Document
from app.models.document_extraction import DocumentExtraction, ExtractionStatus
from app.repositories.extractions import DocumentExtractionRepository
from app.storage.local import LocalStorageProvider
from tests.phase3_helpers import add_member, create_account, create_workspace
from tests.phase5_helpers import (
    DOCX_MIME,
    PDF_MIME,
    create_case,
    create_document_context,
    document_base,
    make_docx,
    make_malformed_docx,
    make_pdf,
)


def extraction_urls(
    workspace: dict[str, Any], legal_case: dict[str, Any], document: dict[str, Any]
) -> tuple[str, str]:
    base = f"{document_base(workspace, legal_case)}/{document['id']}"
    return f"{base}/extract", f"{base}/extraction"


async def extraction_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(DocumentExtraction)) or 0
    )


async def test_pdf_api_persists_metadata_pages_integrity_and_is_idempotent(
    client: AsyncClient,
    session: AsyncSession,
    application,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = make_pdf("Agreement Café § 1: 1,234.50.", "Second page; rights reserved.")
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client,
        "phase5-pdf@example.com",
        content=original,
    )
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)
    record_before = await session.scalar(
        select(Document).where(Document.id == UUID(document["id"]))
    )
    assert record_before is not None
    storage: LocalStorageProvider = application.state.document_storage
    storage_key = record_before.storage_key
    metadata_before = {
        "case_id": record_before.case_id,
        "created_by": record_before.created_by,
        "filename": record_before.original_filename,
        "size": record_before.file_size,
        "sha256": record_before.sha256_hash,
        "storage_key": record_before.storage_key,
    }
    stored_path: Path = storage.resolve_key(storage_key)
    bytes_before = stored_path.read_bytes()

    response = await client.post(trigger_url, headers=headers)
    assert response.status_code == 200, response.text
    extraction = response.json()
    assert extraction["document_id"] == document["id"]
    assert extraction["extractor_type"] == "pymupdf"
    assert extraction["extractor_version"] == version("PyMuPDF")
    assert extraction["status"] == "COMPLETED"
    assert extraction["page_count"] == 2
    assert extraction["parser_metadata"]["method"] == "direct_text"
    assert extraction["parser_metadata"]["direct_text_pages"] == [1, 2]
    assert extraction["parser_metadata"]["ocr_pages"] == []
    assert extraction["text_content"].startswith("[Page 1]\n\n")
    assert "\n\n[Page 2]\n\n" in extraction["text_content"]
    assert extraction["character_count"] == len(extraction["text_content"])
    assert extraction["source_sha256_hash"] == hashlib.sha256(original).hexdigest()
    assert extraction["extracted_at"] is not None
    assert extraction["error_code"] is None
    assert extraction["error_message"] is None
    assert (await client.get(get_url, headers=headers)).json() == extraction

    async def should_not_run(_self, _source):
        raise AssertionError("completed extraction was executed again")

    monkeypatch.setattr(PDFExtractor, "extract", should_not_run)
    repeated = await client.post(trigger_url, headers=headers)
    assert repeated.status_code == 200
    assert repeated.json() == extraction
    assert await extraction_count(session) == 1

    await session.refresh(record_before)
    assert {
        "case_id": record_before.case_id,
        "created_by": record_before.created_by,
        "filename": record_before.original_filename,
        "size": record_before.file_size,
        "sha256": record_before.sha256_hash,
        "storage_key": record_before.storage_key,
    } == metadata_before
    assert stored_path.read_bytes() == bytes_before == original
    assert hashlib.sha256(stored_path.read_bytes()).hexdigest() == document["sha256_hash"]


async def test_docx_api_preserves_structure_unicode_and_has_no_page_count(
    client: AsyncClient,
) -> None:
    original = make_docx(
        heading="Agreement 合同",
        paragraphs=("First paragraph.", "Amount ₹ 5,000; payable."),
        table=(("Party", "Role"), ("ABC", "Buyer"), ("XYZ", "Seller")),
    )
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client,
        "phase5-docx@example.com",
        filename="agreement.docx",
        content=original,
        mime_type=DOCX_MIME,
    )
    trigger_url, _ = extraction_urls(workspace, legal_case, document)

    response = await client.post(trigger_url, headers=headers)
    assert response.status_code == 200, response.text
    extraction = response.json()
    assert extraction["extractor_type"] == "python-docx"
    assert extraction["extractor_version"] == version("python-docx")
    assert extraction["page_count"] is None
    assert extraction["parser_metadata"]["method"] == "direct_text"
    assert extraction["parser_metadata"]["engine"] == "python-docx"
    assert extraction["text_content"] == (
        "Agreement 合同\n\nFirst paragraph.\n\nAmount ₹ 5,000; payable.\n\n"
        "Party | Role\nABC | Buyer\nXYZ | Seller"
    )
    assert extraction["source_sha256_hash"] == document["sha256_hash"]


@pytest.mark.parametrize(
    "original",
    [make_pdf(None), make_pdf(None, draw_image_shape=True)],
    ids=["empty-pdf", "scanned-image-only-pdf"],
)
async def test_textless_pdf_completes_after_ocr_fallback(
    client: AsyncClient,
    original: bytes,
) -> None:
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client,
        f"empty-{hashlib.sha256(original).hexdigest()[:8]}@example.com",
        content=original,
    )
    trigger_url, _ = extraction_urls(workspace, legal_case, document)

    extraction = (await client.post(trigger_url, headers=headers)).json()
    assert extraction["status"] == "COMPLETED"
    assert extraction["text_content"] == ""
    assert extraction["character_count"] == 0
    assert extraction["page_count"] == 1
    assert extraction["extractor_type"] == "tesseract"
    assert extraction["parser_metadata"]["method"] == "ocr"
    assert extraction["parser_metadata"]["ocr_pages"] == [1]


@pytest.mark.parametrize(
    ("filename", "mime_type", "content", "expected_code"),
    [
        ("broken.pdf", PDF_MIME, b"%PDF-corrupted", "DOCUMENT_CORRUPTED"),
        ("broken.docx", DOCX_MIME, make_malformed_docx(), "DOCX_PARSE_ERROR"),
    ],
)
async def test_corrupted_documents_fail_safely_and_persist_error(
    client: AsyncClient,
    filename: str,
    mime_type: str,
    content: bytes,
    expected_code: str,
) -> None:
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client,
        f"corrupt-{expected_code.casefold()}@example.com",
        filename=filename,
        content=content,
        mime_type=mime_type,
    )
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)

    failed = await client.post(trigger_url, headers=headers)
    assert failed.status_code == 422
    assert failed.json() == {"detail": "Document text extraction failed"}
    assert "traceback" not in failed.text.casefold()
    assert "storage" not in failed.text.casefold()
    persisted = (await client.get(get_url, headers=headers)).json()
    assert persisted["status"] == "FAILED"
    assert persisted["error_code"] == expected_code
    assert persisted["error_message"]
    assert persisted["text_content"] == ""
    assert persisted["character_count"] == 0


async def test_failed_extraction_retries_same_record_and_completes(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client,
        "retry-extraction@example.com",
        content=make_pdf("Retry succeeds with sufficient selectable legal agreement text."),
    )
    trigger_url, _ = extraction_urls(workspace, legal_case, document)
    original_extract = PDFExtractor.extract
    attempts = 0

    async def fail_once(self, source):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ExtractionError("PDF_PARSE_ERROR", "The PDF could not be read for text extraction")
        return await original_extract(self, source)

    monkeypatch.setattr(PDFExtractor, "extract", fail_once)
    assert (await client.post(trigger_url, headers=headers)).status_code == 422
    failed_id = (
        await session.scalar(
            select(DocumentExtraction.id).where(
                DocumentExtraction.document_id == UUID(document["id"])
            )
        )
    )

    retried = await client.post(trigger_url, headers=headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "COMPLETED"
    assert "Retry succeeds with sufficient selectable legal agreement text." in retried.json()["text_content"]
    assert UUID(retried.json()["id"]) == failed_id
    assert await extraction_count(session) == 1


@pytest.mark.parametrize(
    ("role", "post_status"),
    [("OWNER", 200), ("ADMIN", 200), ("MEMBER", 200), ("VIEWER", 403)],
)
async def test_extraction_role_matrix(
    client: AsyncClient,
    role: str,
    post_status: int,
) -> None:
    owner, workspace, legal_case, document, owner_headers, _ = await create_document_context(
        client,
        f"role-owner-{role.casefold()}@example.com",
        content=make_pdf("Authorized selectable agreement text remains available to workspace members."),
    )
    del owner
    if role == "OWNER":
        actor_headers = owner_headers
    else:
        actor, actor_headers = await create_account(
            client, f"role-actor-{role.casefold()}@example.com"
        )
        await add_member(client, workspace["id"], owner_headers, actor["email"], role)
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)

    if role == "VIEWER":
        owner_result = await client.post(trigger_url, headers=owner_headers)
        assert owner_result.status_code == 200
    triggered = await client.post(trigger_url, headers=actor_headers)
    assert triggered.status_code == post_status
    viewed = await client.get(get_url, headers=actor_headers)
    assert viewed.status_code == 200
    assert viewed.json()["text_content"].endswith(
        "Authorized selectable agreement text remains available to workspace members."
    )


async def test_non_member_cross_tenant_and_id_mismatches_return_404(
    client: AsyncClient,
) -> None:
    _, workspace_a, case_a, document_a, headers_a, _ = await create_document_context(
        client, "extract-tenant-a@example.com"
    )
    _, workspace_b, case_b, document_b, headers_b, _ = await create_document_context(
        client, "extract-tenant-b@example.com"
    )
    trigger_b, get_b = extraction_urls(workspace_b, case_b, document_b)
    assert (await client.post(trigger_b, headers=headers_b)).status_code == 200

    mismatch_urls = [
        trigger_b,
        get_b,
        f"{document_base(workspace_a, case_a)}/{document_b['id']}/extract",
        f"{document_base(workspace_a, case_a)}/{document_b['id']}/extraction",
        f"{document_base(workspace_a, case_b)}/{document_b['id']}/extract",
        f"{document_base(workspace_a, case_b)}/{document_b['id']}/extraction",
        f"{document_base(workspace_b, case_a)}/{document_a['id']}/extract",
        f"{document_base(workspace_b, case_a)}/{document_a['id']}/extraction",
    ]
    responses = []
    for index, url in enumerate(mismatch_urls):
        method = client.post if index % 2 == 0 else client.get
        responses.append(await method(url, headers=headers_a))
    assert [response.status_code for response in responses] == [404] * len(responses)


async def test_missing_extraction_and_processing_conflict(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client, "processing-extraction@example.com"
    )
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)
    assert (await client.get(get_url, headers=headers)).status_code == 404

    extraction = DocumentExtraction(
        document_id=UUID(document["id"]),
        extractor_type="pymupdf",
        extractor_version=version("PyMuPDF"),
        status=ExtractionStatus.PROCESSING,
        text_content="",
        character_count=0,
        source_sha256_hash=document["sha256_hash"],
    )
    session.add(extraction)
    await session.commit()

    conflict = await client.post(trigger_url, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Document extraction is already in progress"}


async def test_missing_storage_object_records_failure_without_leaking_key(
    client: AsyncClient,
    session: AsyncSession,
    application,
) -> None:
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client, "missing-source@example.com"
    )
    record = await session.scalar(select(Document).where(Document.id == UUID(document["id"])))
    assert record is not None
    storage_key = record.storage_key
    application.state.document_storage.delete(storage_key)
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)

    response = await client.post(trigger_url, headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Document file not found"}
    assert storage_key not in response.text
    failed = (await client.get(get_url, headers=headers)).json()
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "SOURCE_UNAVAILABLE"


async def test_completion_persistence_failure_is_controlled_and_original_is_intact(
    client: AsyncClient,
    session: AsyncSession,
    application,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, legal_case, document, headers, original = await create_document_context(
        client,
        "extraction-db-failure@example.com",
        content=make_pdf("Persistence failure fixture contains sufficient selectable legal text."),
    )
    record = await session.scalar(select(Document).where(Document.id == UUID(document["id"])))
    assert record is not None
    stored_path = application.state.document_storage.resolve_key(record.storage_key)
    original_save = DocumentExtractionRepository.save

    async def fail_completed(self, extraction):
        if extraction.status == ExtractionStatus.COMPLETED:
            raise RuntimeError("simulated database failure")
        return await original_save(self, extraction)

    monkeypatch.setattr(DocumentExtractionRepository, "save", fail_completed)
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)
    response = await client.post(trigger_url, headers=headers)

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to complete document extraction"}
    assert "simulated" not in response.text
    assert stored_path.read_bytes() == original
    assert hashlib.sha256(original).hexdigest() == document["sha256_hash"]
    failed = (await client.get(get_url, headers=headers)).json()
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "EXTRACTION_ERROR"
