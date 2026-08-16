from __future__ import annotations

import asyncio
from importlib.metadata import version
from typing import BinaryIO

import pymupdf

from app.documents.extractors.base import (
    DocumentExtractor,
    ExtractedDocument,
    ExtractedPage,
    ExtractionError,
)


class PDFExtractor(DocumentExtractor):
    """Local, read-only PyMuPDF extraction with one result per PDF page."""

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

    @staticmethod
    def _extract(source: BinaryIO) -> ExtractedDocument:
        try:
            source.seek(0)
            # PyMuPDF's stream API requires a bytes-like object. The original is
            # read once and is never opened for writing or modified.
            pdf_bytes = source.read()
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
                pages = tuple(
                    ExtractedPage(
                        page_number=index + 1,
                        text=pdf.load_page(index).get_text("text", sort=True),
                    )
                    for index in range(pdf.page_count)
                )
                return ExtractedDocument(pages=pages, page_count=pdf.page_count)
        except Exception as exc:
            raise ExtractionError(
                "PDF_PARSE_ERROR",
                "The PDF could not be read for text extraction",
            ) from exc
