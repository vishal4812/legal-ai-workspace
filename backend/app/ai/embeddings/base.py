from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Provider-neutral batch embedding boundary."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector size produced by this provider."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable provider identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured model identifier."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed passages while preserving input order."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed one search query."""


class EmbeddingError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
