from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, BinaryIO


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    pages: tuple[ExtractedPage, ...]
    page_count: int | None
    extractor_type: str | None = None
    extractor_version: str | None = None
    parser_metadata: dict[str, Any] = field(default_factory=dict)


class ExtractionError(Exception):
    """A parser failure that is safe for the service layer to categorize."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        page_count: int | None = None,
        parser_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.page_count = page_count
        self.parser_metadata = parser_metadata or {}


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
