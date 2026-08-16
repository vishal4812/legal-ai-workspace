from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    pages: tuple[ExtractedPage, ...]
    page_count: int | None


class ExtractionError(Exception):
    """A parser failure that is safe for the service layer to categorize."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class DocumentExtractor(ABC):
    """Extract text while retaining stable one-based page information."""

    @property
    @abstractmethod
    def extractor_type(self) -> str:
        """Return the parser package name persisted with an extraction."""

    @property
    @abstractmethod
    def extractor_version(self) -> str:
        """Return the installed parser package version."""

    @abstractmethod
    def supports(self, media_type: str) -> bool:
        """Return whether this extractor handles the media type."""

    @abstractmethod
    async def extract(self, source: BinaryIO) -> ExtractedDocument:
        """Read an immutable original through a controlled storage handle."""
