from __future__ import annotations

import asyncio
from importlib.metadata import version
from typing import BinaryIO

from docx import Document as WordDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.documents.extractors.base import (
    DocumentExtractor,
    ExtractedDocument,
    ExtractedPage,
    ExtractionError,
)


class DOCXExtractor(DocumentExtractor):
    """Extract DOCX paragraphs and tables in deterministic body order."""

    @property
    def extractor_type(self) -> str:
        return "python-docx"

    @property
    def extractor_version(self) -> str:
        return version("python-docx")

    def supports(self, media_type: str) -> bool:
        return media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    async def extract(self, source: BinaryIO) -> ExtractedDocument:
        return await asyncio.to_thread(self._extract, source)

    @staticmethod
    def _extract(source: BinaryIO) -> ExtractedDocument:
        try:
            source.seek(0)
            document = WordDocument(source)
            blocks: list[str] = []
            for item in document.iter_inner_content():
                if isinstance(item, Paragraph):
                    blocks.append(item.text)
                elif isinstance(item, Table):
                    rows = [
                        " | ".join(cell.text for cell in row.cells)
                        for row in item.rows
                    ]
                    blocks.append("\n".join(rows))
            return ExtractedDocument(
                pages=(ExtractedPage(page_number=1, text="\n\n".join(blocks)),),
                page_count=None,
                extractor_type="python-docx",
                extractor_version=version("python-docx"),
                parser_metadata={
                    "method": "direct_text",
                    "engine": "python-docx",
                    "engine_version": version("python-docx"),
                },
            )
        except Exception as exc:
            raise ExtractionError(
                "DOCX_PARSE_ERROR",
                "The DOCX file could not be read for text extraction",
            ) from exc
