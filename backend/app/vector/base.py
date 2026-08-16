from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class VectorPoint:
    id: UUID
    vector: list[float]
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class VectorHit:
    id: UUID
    score: float
    payload: dict[str, object]


class VectorStoreError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class VectorStore(ABC):
    @property
    @abstractmethod
    def collection_name(self) -> str:
        """Return the configured collection name."""

    @abstractmethod
    async def ensure_collection(self, dimension: int) -> None:
        """Create a missing compatible collection or validate the existing one."""

    @abstractmethod
    async def replace_document_points(
        self, document_id: UUID, points: list[VectorPoint]
    ) -> None:
        """Delete previous document points and upsert the supplied points in batches."""

    @abstractmethod
    async def count_document_points(self, document_id: UUID) -> int:
        """Count stored points for one document."""

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        workspace_id: UUID,
        case_id: UUID | None,
        limit: int,
    ) -> list[VectorHit]:
        """Search using mandatory workspace and optional case payload filters."""

    @abstractmethod
    async def close(self) -> None:
        """Release provider transport resources."""
