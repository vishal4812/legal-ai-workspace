from __future__ import annotations

import asyncio
import math
from importlib.metadata import version
from time import monotonic
from typing import Any, BinaryIO

import pymupdf
from PIL import Image

from app.documents.extractors.base import (
    DocumentExtractor,
    ExtractedDocument,
    ExtractedPage,
    ExtractionError,
)
from app.documents.ocr.base import OCRError, OCRProvider, OCRRuntimeInfo
from app.documents.ocr.detection import is_meaningful_text


class PDFExtractor(DocumentExtractor):
    """Page-aware PyMuPDF extraction with a bounded local OCR fallback."""

    def __init__(
        self,
        *,
        ocr_provider: OCRProvider | None = None,
        ocr_enabled: bool = False,
        ocr_language: str = "eng",
        ocr_dpi: int = 200,
        ocr_max_pages: int = 100,
        ocr_timeout_seconds: int = 120,
        ocr_max_image_pixels: int = 25_000_000,
    ) -> None:
        self._ocr_provider = ocr_provider
        self._ocr_enabled = ocr_enabled
        self._ocr_language = ocr_language
        self._ocr_dpi = ocr_dpi
        self._ocr_max_pages = ocr_max_pages
        self._ocr_timeout_seconds = ocr_timeout_seconds
        self._ocr_max_image_pixels = ocr_max_image_pixels

    @property
    def extractor_type(self) -> str:
        return "pymupdf"

    @property
    def extractor_version(self) -> str:
        return version("PyMuPDF")

    def supports(self, media_type: str) -> bool:
        return media_type == "application/pdf"

    async def extract(self, source: BinaryIO) -> ExtractedDocument:
        return await asyncio.to_thread(self._extract, source)

    def _extract(self, source: BinaryIO) -> ExtractedDocument:
        try:
            source.seek(0)
            # PyMuPDF's stream API requires bytes. The original is read once,
            # opened read-only, and never written back to storage.
            pdf_bytes = source.read()
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
                return self._extract_pdf(pdf)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(
                "DOCUMENT_CORRUPTED",
                "The PDF could not be read for text extraction",
            ) from exc

    def _extract_pdf(self, pdf: pymupdf.Document) -> ExtractedDocument:
        pymupdf_version = self.extractor_version
        if self._ocr_enabled and pdf.page_count > self._ocr_max_pages:
            raise ExtractionError(
                "OCR_PAGE_LIMIT_EXCEEDED",
                "The document exceeds the configured OCR page limit",
                page_count=pdf.page_count,
                parser_metadata={
                    "method": "undetermined",
                    "direct_text_engine": "pymupdf",
                    "direct_text_engine_version": pymupdf_version,
                    "language": self._ocr_language,
                    "dpi": self._ocr_dpi,
                    "direct_text_pages": [],
                    "ocr_pages": [],
                },
            )
        direct_text: dict[int, str] = {}
        ocr_page_numbers: list[int] = []

        for index in range(pdf.page_count):
            page_number = index + 1
            try:
                page_text = pdf.load_page(index).get_text("text", sort=True)
            except Exception as exc:
                raise ExtractionError(
                    "DOCUMENT_CORRUPTED",
                    "The PDF could not be read for text extraction",
                    page_count=pdf.page_count,
                ) from exc
            direct_text[page_number] = page_text
            if not is_meaningful_text(page_text):
                ocr_page_numbers.append(page_number)

        direct_page_numbers = [
            page_number
            for page_number in range(1, pdf.page_count + 1)
            if page_number not in ocr_page_numbers
        ]
        if not ocr_page_numbers:
            return ExtractedDocument(
                pages=tuple(
                    ExtractedPage(page_number=number, text=direct_text[number])
                    for number in range(1, pdf.page_count + 1)
                ),
                page_count=pdf.page_count,
                extractor_type="pymupdf",
                extractor_version=pymupdf_version,
                parser_metadata={
                    "method": "direct_text",
                    "engine": "pymupdf",
                    "engine_version": pymupdf_version,
                    "direct_text_pages": direct_page_numbers,
                    "ocr_pages": [],
                },
            )

        method = "ocr" if len(ocr_page_numbers) == pdf.page_count else "mixed"
        metadata: dict[str, Any] = {
            "method": method,
            "direct_text_engine": "pymupdf",
            "direct_text_engine_version": pymupdf_version,
            "language": self._ocr_language,
            "dpi": self._ocr_dpi,
            "direct_text_pages": direct_page_numbers,
            "ocr_pages": ocr_page_numbers,
        }
        if not self._ocr_enabled:
            raise ExtractionError(
                "OCR_DISABLED",
                "Local OCR is disabled on this server",
                page_count=pdf.page_count,
                parser_metadata=metadata,
            )
        if self._ocr_provider is None:
            raise ExtractionError(
                "OCR_UNAVAILABLE",
                "Local OCR is unavailable on this server",
                page_count=pdf.page_count,
                parser_metadata=metadata,
            )
        deadline = monotonic() + self._ocr_timeout_seconds
        try:
            runtime = self._ocr_provider.verify(self._remaining_seconds(deadline))
        except OCRError as exc:
            raise self._extraction_error(exc, pdf.page_count, metadata) from exc
        except Exception as exc:
            raise ExtractionError(
                "OCR_PROCESSING_FAILED",
                "The document could not be processed by local OCR",
                page_count=pdf.page_count,
                parser_metadata=metadata,
            ) from exc
        metadata.update(
            {
                "engine": runtime.engine,
                "engine_version": runtime.version,
                "language": runtime.language,
            }
        )

        page_text = dict(direct_text)
        for page_number in ocr_page_numbers:
            remaining = self._remaining_seconds(deadline)
            if remaining <= 0:
                raise ExtractionError(
                    "OCR_TIMEOUT",
                    "OCR exceeded the configured time limit",
                    page_count=pdf.page_count,
                    parser_metadata=metadata,
                )
            try:
                page = pdf.load_page(page_number - 1)
                width = math.ceil(page.rect.width * self._ocr_dpi / 72)
                height = math.ceil(page.rect.height * self._ocr_dpi / 72)
            except Exception as exc:
                raise ExtractionError(
                    "OCR_RENDER_FAILED",
                    "A PDF page could not be rendered for OCR",
                    page_count=pdf.page_count,
                    parser_metadata=metadata,
                ) from exc
            if width * height > self._ocr_max_image_pixels:
                raise ExtractionError(
                    "OCR_IMAGE_LIMIT_EXCEEDED",
                    "A PDF page exceeds the configured OCR image limit",
                    page_count=pdf.page_count,
                    parser_metadata=metadata,
                )
            try:
                pixmap = page.get_pixmap(
                    dpi=self._ocr_dpi,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )
                image.info["dpi"] = (self._ocr_dpi, self._ocr_dpi)
            except Exception as exc:
                raise ExtractionError(
                    "OCR_RENDER_FAILED",
                    "A PDF page could not be rendered for OCR",
                    page_count=pdf.page_count,
                    parser_metadata=metadata,
                ) from exc
            try:
                page_text[page_number] = self._ocr_provider.recognize(
                    image,
                    self._remaining_seconds(deadline),
                )
            except OCRError as exc:
                raise self._extraction_error(exc, pdf.page_count, metadata) from exc
            except Exception as exc:
                raise ExtractionError(
                    "OCR_PROCESSING_FAILED",
                    "The page could not be processed by local OCR",
                    page_count=pdf.page_count,
                    parser_metadata=metadata,
                ) from exc
            finally:
                image.close()
                del image
                del pixmap

        extractor_type, extractor_version = self._result_extractor(runtime, method)
        return ExtractedDocument(
            pages=tuple(
                ExtractedPage(page_number=number, text=page_text[number])
                for number in range(1, pdf.page_count + 1)
            ),
            page_count=pdf.page_count,
            extractor_type=extractor_type,
            extractor_version=extractor_version,
            parser_metadata=metadata,
        )

    @staticmethod
    def _remaining_seconds(deadline: float) -> float:
        return max(0.0, deadline - monotonic())

    @staticmethod
    def _extraction_error(
        error: OCRError,
        page_count: int,
        metadata: dict[str, Any],
    ) -> ExtractionError:
        return ExtractionError(
            error.code,
            error.safe_message,
            page_count=page_count,
            parser_metadata=metadata,
        )

    def _result_extractor(
        self,
        runtime: OCRRuntimeInfo,
        method: str,
    ) -> tuple[str, str]:
        if method == "ocr":
            return "tesseract", runtime.version
        return (
            "pymupdf+tesseract",
            f"{self.extractor_version}+{runtime.version}"[:50],
        )
