from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    pages: tuple[ExtractedPage, ...]


class DocumentExtractor(ABC):
    """Extract text while retaining stable one-based page information."""

    @abstractmethod
    def supports(self, media_type: str) -> bool:
        """Return whether this extractor handles the media type."""

    @abstractmethod
    async def extract(self, source: Path) -> ExtractedDocument:
        """Extract text from a private local source."""
