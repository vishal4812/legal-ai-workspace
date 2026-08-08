from pathlib import Path

from app.documents.extractors.base import DocumentExtractor, ExtractedDocument


class PDFExtractor(DocumentExtractor):
    """PDF boundary; extraction is intentionally deferred to Phase 5."""

    def supports(self, media_type: str) -> bool:
        return media_type == "application/pdf"

    async def extract(self, source: Path) -> ExtractedDocument:
        raise NotImplementedError("PDF extraction is scheduled for Phase 5")
