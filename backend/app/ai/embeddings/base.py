from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Provider-neutral batch embedding boundary."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector size produced by this provider."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed text while preserving input order."""
