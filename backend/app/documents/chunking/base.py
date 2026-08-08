from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.documents.extractors.base import ExtractedDocument


@dataclass(frozen=True, slots=True)
class Chunk:
    index: int
    text: str
    page_from: int
    page_to: int


class Chunker(ABC):
    """Page-aware document chunking boundary."""

    @abstractmethod
    def chunk(self, document: ExtractedDocument) -> list[Chunk]:
        """Create ordered chunks with page ranges."""
