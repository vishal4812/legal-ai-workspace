from __future__ import annotations

import hashlib
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extractors.base import ExtractionError
from app.documents.extractors.normalization import render_extracted_text
from app.documents.extractors.pdf import PDFExtractor
from app.documents.ocr.base import OCRError, OCRProvider, OCRRuntimeInfo
from app.documents.ocr.detection import is_meaningful_text, measure_text_quality
from app.documents.ocr.tesseract import TesseractOCRProvider
from app.models.document import Document
from app.models.document_extraction import DocumentExtraction
from tests.phase5_helpers import (
    create_document_context,
    document_base,
    make_mixed_pdf,
    make_pdf,
    make_scanned_pdf,
)


class FakeOCRProvider(OCRProvider):
    def __init__(
        self,
        results: list[str] | None = None,
        error: OCRError | None = None,
    ) -> None:
        self.results = list(results or [])
        self.error = error
        self.verify_calls = 0
        self.images: list[tuple[int, int]] = []
        self.timeouts: list[float] = []

    def verify(self, timeout_seconds: float) -> OCRRuntimeInfo:
        self.verify_calls += 1
        if self.error is not None:
            raise self.error
        return OCRRuntimeInfo(engine="tesseract", version="5.3.0", language="eng")

    def recognize(self, image: Image.Image, timeout_seconds: float) -> str:
        self.images.append(image.size)
        self.timeouts.append(timeout_seconds)
        if self.error is not None:
            raise self.error
        return self.results.pop(0) if self.results else ""


def configured_pdf_extractor(
    provider: OCRProvider,
    **overrides: Any,
) -> PDFExtractor:
    values = {
        "ocr_provider": provider,
        "ocr_enabled": True,
        "ocr_language": "eng",
        "ocr_dpi": 200,
        "ocr_max_pages": 100,
        "ocr_timeout_seconds": 120,
        "ocr_max_image_pixels": 25_000_000,
    }
    values.update(overrides)
    return PDFExtractor(**values)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", False),
        ("  12  ", False),
        ("Page 4", False),
        ("@#$%^&*()_+={}[]<>!~" * 3, False),
        ("This Agreement is binding upon both parties.", True),
        ("Clause 12 requires payment of 1,234.50 dollars.", True),
    ],
)
def test_text_sufficiency_heuristic_is_deterministic(text: str, expected: bool) -> None:
    assert is_meaningful_text(text) is expected
    assert measure_text_quality(text) == measure_text_quality(text)


async def test_normal_pdf_does_not_invoke_ocr() -> None:
    provider = FakeOCRProvider(error=AssertionError("OCR must not run"))  # type: ignore[arg-type]
    result = await configured_pdf_extractor(provider).extract(
        io.BytesIO(make_pdf("This Agreement is binding upon both parties and their successors."))
    )

    assert provider.verify_calls == 0
    assert provider.images == []
    assert result.extractor_type == "pymupdf"
    assert result.parser_metadata == {
        "method": "direct_text",
        "engine": "pymupdf",
        "engine_version": result.extractor_version,
        "direct_text_pages": [1],
        "ocr_pages": [],
    }


async def test_scanned_pdf_uses_ocr_and_preserves_normalized_page_boundaries() -> None:
    provider = FakeOCRProvider(["  FIRST   SCANNED PAGE\r\nClause  1.  ", "SECOND PAGE\x00\n\n\nEnd."])
    result = await configured_pdf_extractor(provider).extract(
        io.BytesIO(make_scanned_pdf("FIRST SCANNED PAGE", "SECOND SCANNED PAGE"))
    )

    assert provider.verify_calls == 1
    assert len(provider.images) == 2
    assert render_extracted_text(result) == (
        "[Page 1]\n\nFIRST SCANNED PAGE\nClause 1.\n\n"
        "[Page 2]\n\nSECOND PAGE\n\nEnd."
    )
    assert result.page_count == 2
    assert result.extractor_type == "tesseract"
    assert result.extractor_version == "5.3.0"
    assert result.parser_metadata["method"] == "ocr"
    assert result.parser_metadata["ocr_pages"] == [1, 2]
    assert result.parser_metadata["direct_text_pages"] == []
    assert result.parser_metadata["language"] == "eng"
    assert result.parser_metadata["dpi"] == 200


async def test_mixed_pdf_ocrs_only_insufficient_page() -> None:
    direct = "This Agreement contains sufficient selectable text on the first page."
    provider = FakeOCRProvider(["OCR text from the scanned second page."])
    result = await configured_pdf_extractor(provider).extract(
        io.BytesIO(make_mixed_pdf(direct, "SCANNED SECOND PAGE AGREEMENT"))
    )
    rendered = render_extracted_text(result)

    assert len(provider.images) == 1
    assert result.extractor_type == "pymupdf+tesseract"
    assert result.parser_metadata["method"] == "mixed"
    assert result.parser_metadata["direct_text_pages"] == [1]
    assert result.parser_metadata["ocr_pages"] == [2]
    assert rendered == (
        f"[Page 1]\n\n{direct}\n\n"
        "[Page 2]\n\nOCR text from the scanned second page."
    )


async def test_unicode_ocr_output_is_preserved_without_correction() -> None:
    provider = FakeOCRProvider(["合同 Café § 2 — राशि ₹ 5,000.00"])
    result = await configured_pdf_extractor(provider).extract(
        io.BytesIO(make_scanned_pdf("UNICODE SCANNED FIXTURE"))
    )

    assert "合同 Café § 2 — राशि ₹ 5,000.00" in render_extracted_text(result)


async def test_dpi_is_honored_and_page_images_are_released_sequentially() -> None:
    provider = FakeOCRProvider(["First", "Second"])
    result = await configured_pdf_extractor(provider, ocr_dpi=144).extract(
        io.BytesIO(make_scanned_pdf("FIRST", "SECOND"))
    )

    assert result.parser_metadata["dpi"] == 144
    assert len(provider.images) == 2
    assert all(width < 1300 and height < 1800 for width, height in provider.images)
    assert all(timeout > 0 for timeout in provider.timeouts)


async def test_ocr_page_and_render_limits_fail_before_recognition() -> None:
    page_provider = FakeOCRProvider(["unused"])
    with pytest.raises(ExtractionError) as page_error:
        await configured_pdf_extractor(page_provider, ocr_max_pages=1).extract(
            io.BytesIO(make_scanned_pdf("ONE", "TWO"))
        )
    assert page_error.value.code == "OCR_PAGE_LIMIT_EXCEEDED"
    assert page_provider.verify_calls == 0

    image_provider = FakeOCRProvider(["unused"])
    with pytest.raises(ExtractionError) as image_error:
        await configured_pdf_extractor(
            image_provider,
            ocr_max_image_pixels=1_000_000,
        ).extract(io.BytesIO(make_scanned_pdf("OVERSIZED RENDER")))
    assert image_error.value.code == "OCR_IMAGE_LIMIT_EXCEEDED"
    assert image_provider.images == []


@pytest.mark.parametrize(
    ("error_code", "safe_message"),
    [
        ("OCR_UNAVAILABLE", "Local OCR is unavailable on this server"),
        ("OCR_LANGUAGE_UNAVAILABLE", "The configured OCR language is not installed"),
        ("OCR_TIMEOUT", "OCR exceeded the configured time limit"),
        ("OCR_PROCESSING_FAILED", "The page could not be processed by local OCR"),
    ],
)
async def test_ocr_provider_failures_are_bounded(
    error_code: str,
    safe_message: str,
) -> None:
    provider = FakeOCRProvider(error=OCRError(error_code, safe_message))
    with pytest.raises(ExtractionError) as error:
        await configured_pdf_extractor(provider).extract(
            io.BytesIO(make_scanned_pdf("SCANNED FAILURE FIXTURE"))
        )
    assert error.value.code == error_code
    assert error.value.safe_message == safe_message
    assert "path" not in error.value.safe_message.casefold()


async def test_real_tesseract_makes_scanned_text_searchable(application) -> None:
    original = make_scanned_pdf("SCANNED LEGAL AGREEMENT NUMBER 12345")
    extractor = PDFExtractor(
        ocr_provider=application.state.ocr_provider,
        ocr_enabled=True,
        ocr_language=application.state.settings.ocr_lang,
        ocr_dpi=application.state.settings.ocr_dpi,
        ocr_max_pages=application.state.settings.ocr_max_pages,
        ocr_timeout_seconds=application.state.settings.ocr_timeout_seconds,
        ocr_max_image_pixels=application.state.settings.ocr_max_image_pixels,
    )
    result = await extractor.extract(io.BytesIO(original))
    rendered = render_extracted_text(result).upper()

    assert result.parser_metadata["method"] == "ocr"
    assert result.parser_metadata["engine"] == "tesseract"
    assert "SCANNED LEGAL AGREEMENT" in rendered
    assert "12345" in rendered


def test_tesseract_provider_verifies_actual_language_and_captures_version() -> None:
    provider = TesseractOCRProvider("eng")
    runtime = provider.verify(10)

    assert runtime.engine == "tesseract"
    assert runtime.language == "eng"
    assert runtime.version
    assert "tesseract" not in runtime.version.casefold()


def test_tesseract_provider_rejects_missing_language_without_fallback() -> None:
    provider = TesseractOCRProvider("definitely_missing_language")
    with pytest.raises(OCRError) as error:
        provider.verify(10)

    assert error.value.code == "OCR_LANGUAGE_UNAVAILABLE"
    assert provider._runtime_info is None


def test_tesseract_provider_maps_missing_binary_and_timeout_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TesseractOCRProvider("eng")

    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("/private/server/path/tesseract")

    monkeypatch.setattr(subprocess, "run", unavailable)
    with pytest.raises(OCRError) as unavailable_error:
        provider.verify(1)
    assert unavailable_error.value.code == "OCR_UNAVAILABLE"
    assert "/private" not in unavailable_error.value.safe_message

    def timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["tesseract"], 1)

    monkeypatch.setattr(subprocess, "run", timed_out)
    with pytest.raises(OCRError) as timeout_error:
        provider.verify(1)
    assert timeout_error.value.code == "OCR_TIMEOUT"


def test_tesseract_recognition_timeout_is_bounded_and_temp_files_are_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TesseractOCRProvider("eng")
    provider._runtime_info = OCRRuntimeInfo("tesseract", "5.3.0", "eng")
    image = Image.new("RGB", (200, 100), "white")
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    def timeout(*_args, **_kwargs):
        raise RuntimeError("private process timeout details")

    monkeypatch.setattr("app.documents.ocr.tesseract.pytesseract.image_to_string", timeout)
    with pytest.raises(OCRError) as error:
        provider.recognize(image, 1)
    image.close()

    assert error.value.code == "OCR_TIMEOUT"
    assert error.value.safe_message == "OCR exceeded the configured time limit"
    assert list(tmp_path.iterdir()) == []


def test_tesseract_removes_its_temporary_page_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TesseractOCRProvider("eng")
    image = Image.new("RGB", (300, 120), "white")
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    assert provider.recognize(image, 10) == ""
    image.close()
    assert list(tmp_path.iterdir()) == []


def extraction_urls(
    workspace: dict[str, Any], legal_case: dict[str, Any], document: dict[str, Any]
) -> tuple[str, str]:
    base = f"{document_base(workspace, legal_case)}/{document['id']}"
    return f"{base}/extract", f"{base}/extraction"


async def test_ocr_failure_retry_reuses_row_and_preserves_original(
    client,
    application,
    session: AsyncSession,
) -> None:
    original = make_scanned_pdf("RETRYABLE SCANNED LEGAL AGREEMENT")
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client,
        "phase6-retry@example.com",
        content=original,
    )
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)
    record = await session.scalar(select(Document).where(Document.id == UUID(document["id"])))
    assert record is not None
    stored_path: Path = application.state.document_storage.resolve_key(record.storage_key)
    sha_before = record.sha256_hash
    bytes_before = stored_path.read_bytes()

    application.state.ocr_provider = FakeOCRProvider(
        error=OCRError("OCR_TIMEOUT", "OCR exceeded the configured time limit")
    )
    failed_response = await client.post(trigger_url, headers=headers)
    assert failed_response.status_code == 422
    failed = (await client.get(get_url, headers=headers)).json()
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "OCR_TIMEOUT"
    assert failed["parser_metadata"]["method"] == "ocr"
    extraction_id = failed["id"]

    application.state.ocr_provider = FakeOCRProvider(["RETRYABLE SCANNED LEGAL AGREEMENT"])
    retried_response = await client.post(trigger_url, headers=headers)
    assert retried_response.status_code == 200, retried_response.text
    retried = retried_response.json()
    assert retried["id"] == extraction_id
    assert retried["status"] == "COMPLETED"
    assert retried["parser_metadata"]["method"] == "ocr"
    assert retried["source_sha256_hash"] == sha_before == hashlib.sha256(original).hexdigest()
    assert stored_path.read_bytes() == bytes_before == original
    await session.refresh(record)
    assert record.sha256_hash == sha_before
    assert int(await session.scalar(select(func.count()).select_from(DocumentExtraction)) or 0) == 1


async def test_api_page_limit_is_persisted_without_partial_completion(
    client,
    application,
) -> None:
    original = make_scanned_pdf("FIRST SCANNED PAGE", "SECOND SCANNED PAGE")
    _, workspace, legal_case, document, headers, _ = await create_document_context(
        client,
        "phase6-page-limit@example.com",
        content=original,
    )
    trigger_url, get_url = extraction_urls(workspace, legal_case, document)
    application.state.settings.ocr_max_pages = 1
    provider = FakeOCRProvider(["unused"])
    application.state.ocr_provider = provider

    response = await client.post(trigger_url, headers=headers)
    failed = (await client.get(get_url, headers=headers)).json()
    assert response.status_code == 422
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "OCR_PAGE_LIMIT_EXCEEDED"
    assert failed["text_content"] == ""
    assert failed["page_count"] == 2
    assert provider.verify_calls == 0
    assert "storage" not in response.text.casefold()
