from __future__ import annotations

import io
from importlib.metadata import version

import pytest

from app.documents.extractors.base import ExtractionError
from app.documents.extractors.docx import DOCXExtractor
from app.documents.extractors.normalization import normalize_text, render_extracted_text
from app.documents.extractors.pdf import PDFExtractor
from tests.phase5_helpers import make_docx, make_malformed_docx, make_pdf


async def test_pdf_extractor_preserves_pages_unicode_numbers_and_legal_punctuation() -> None:
    extractor = PDFExtractor()
    result = await extractor.extract(
        io.BytesIO(
            make_pdf(
                "Agreement Café § 1. Purchase price: 1,234.50.",
                "Clause 2: Party A's duties; Party B's rights (reserved).",
            )
        )
    )

    assert result.page_count == 2
    assert [page.page_number for page in result.pages] == [1, 2]
    rendered = render_extracted_text(result)
    assert rendered.startswith("[Page 1]\n\n")
    assert "Café § 1. Purchase price: 1,234.50." in rendered
    assert "\n\n[Page 2]\n\n" in rendered
    assert "Party A's duties; Party B's rights (reserved)." in rendered
    assert extractor.extractor_type == "pymupdf"
    assert extractor.extractor_version == version("PyMuPDF")


@pytest.mark.parametrize(
    "content",
    [make_pdf(None), make_pdf(None, draw_image_shape=True)],
    ids=["empty", "image-only"],
)
async def test_pdf_extractor_requires_enabled_ocr_for_textless_pages(content: bytes) -> None:
    with pytest.raises(ExtractionError) as error:
        await PDFExtractor().extract(io.BytesIO(content))

    assert error.value.code == "OCR_DISABLED"
    assert error.value.page_count == 1


async def test_pdf_extractor_controls_malformed_input() -> None:
    with pytest.raises(ExtractionError) as error:
        await PDFExtractor().extract(io.BytesIO(b"%PDF-corrupted"))
    assert error.value.code == "DOCUMENT_CORRUPTED"
    assert "path" not in error.value.safe_message.casefold()


async def test_docx_extractor_preserves_heading_paragraph_table_order_and_unicode() -> None:
    content = make_docx(
        heading="Agreement 合同",
        paragraphs=("This agreement is entered into…", "Definitions § 2"),
        table=(("Party", "Role"), ("ABC", "Buyer"), ("XYZ", "Seller")),
    )
    extractor = DOCXExtractor()
    result = await extractor.extract(io.BytesIO(content))
    rendered = render_extracted_text(result)

    assert result.page_count is None
    assert rendered == (
        "Agreement 合同\n\n"
        "This agreement is entered into…\n\n"
        "Definitions § 2\n\n"
        "Party | Role\nABC | Buyer\nXYZ | Seller"
    )
    assert extractor.extractor_type == "python-docx"
    assert extractor.extractor_version == version("python-docx")


async def test_empty_and_malformed_docx_are_handled_deterministically() -> None:
    empty = await DOCXExtractor().extract(io.BytesIO(make_docx()))
    assert render_extracted_text(empty) == ""

    with pytest.raises(ExtractionError) as error:
        await DOCXExtractor().extract(io.BytesIO(make_malformed_docx()))
    assert error.value.code == "DOCX_PARSE_ERROR"


def test_normalization_removes_parser_noise_without_changing_legal_content() -> None:
    assert normalize_text("Clause\x00  1\r\n\r\n\r\nAmount:\t1,000.00; due.") == (
        "Clause 1\n\nAmount: 1,000.00; due."
    )
