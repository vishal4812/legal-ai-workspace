from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO


class StagedWrite(ABC):
    """A private, incomplete object that can be validated before publication."""

    @abstractmethod
    def write(self, chunk: bytes) -> None: ...

    @abstractmethod
    def open(self) -> BinaryIO: ...

    @abstractmethod
    def commit(self, storage_key: str) -> None: ...

    @abstractmethod
    def discard(self) -> None: ...


class StorageProvider(ABC):
    """Provider-neutral operations required by the document vault."""

    @abstractmethod
    def stage(self) -> StagedWrite: ...

    @abstractmethod
    def open(self, storage_key: str) -> BinaryIO: ...

    @abstractmethod
    def exists(self, storage_key: str) -> bool: ...

    @abstractmethod
    def size(self, storage_key: str) -> int: ...

    @abstractmethod
    def delete(self, storage_key: str) -> None: ...
