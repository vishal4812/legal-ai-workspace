from pathlib import Path

from app.documents.extractors.base import DocumentExtractor, ExtractedDocument


class DOCXExtractor(DocumentExtractor):
    """DOCX boundary; extraction is intentionally deferred to Phase 5."""

    def supports(self, media_type: str) -> bool:
        return media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    async def extract(self, source: Path) -> ExtractedDocument:
        raise NotImplementedError("DOCX extraction is scheduled for Phase 5")
