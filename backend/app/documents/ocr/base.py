from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL.Image import Image


@dataclass(frozen=True, slots=True)
class OCRRuntimeInfo:
    engine: str
    version: str
    language: str


class OCRError(Exception):
    """A bounded OCR failure whose message is safe to persist and return."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class OCRProvider(ABC):
    """Provider-neutral OCR boundary for one in-memory page image at a time."""

    @abstractmethod
    def verify(self, timeout_seconds: float) -> OCRRuntimeInfo:
        """Verify the engine and configured language without changing app health."""

    @abstractmethod
    def recognize(self, image: Image, timeout_seconds: float) -> str:
        """Recognize one page within the supplied remaining time budget."""
