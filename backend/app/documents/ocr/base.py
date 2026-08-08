from __future__ import annotations

from abc import ABC, abstractmethod


class OCRProvider(ABC):
    """OCR boundary for page images; implementation is deferred to Phase 6."""

    @abstractmethod
    async def recognize(self, image: bytes) -> str:
        """Recognize text in one encoded page image."""
