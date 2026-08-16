from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Chunk:
    index: int
    content: str
    token_count: int
    page_start: int | None
    page_end: int | None


class Chunker(ABC):
    """Page-aware document chunking boundary."""

    @abstractmethod
    def chunk(self, text: str) -> list[Chunk]:
        """Create deterministic ordered chunks from normalized extraction text."""
