from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from app.storage.base import StagedWrite, StorageProvider


class StorageError(Exception):
    """A controlled private-storage failure."""


class InvalidStorageKeyError(StorageError):
    """Raised when an object key could escape or ambiguously address the root."""


class LocalStagedWrite(StagedWrite):
    def __init__(self, provider: "LocalStorageProvider") -> None:
        self._provider = provider
        staging_dir = provider.root / ".staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        temporary = NamedTemporaryFile(mode="w+b", dir=staging_dir, delete=False)
        self._path: Path | None = Path(temporary.name)
        self._file: BinaryIO | None = temporary

    def write(self, chunk: bytes) -> None:
        if self._file is None:
            raise StorageError("Staged object is no longer writable")
        try:
            self._file.write(chunk)
        except OSError as exc:
            raise StorageError("Unable to write staged object") from exc

    def open(self) -> BinaryIO:
        if self._path is None:
            raise StorageError("Staged object is no longer available")
        try:
            if self._file is not None:
                self._file.flush()
                os.fsync(self._file.fileno())
            return self._path.open("rb")
        except OSError as exc:
            raise StorageError("Unable to read staged object") from exc

    def commit(self, storage_key: str) -> None:
        if self._path is None:
            raise StorageError("Staged object is no longer available")
        destination = self._provider.resolve_key(storage_key)
        try:
            if self._file is not None:
                self._file.flush()
                os.fsync(self._file.fileno())
                self._file.close()
                self._file = None
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(self._path, destination)
            self._path = None
        except OSError as exc:
            raise StorageError("Unable to publish staged object") from exc

    def discard(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None
        if self._path is not None:
            try:
                self._path.unlink(missing_ok=True)
            except OSError as exc:
                raise StorageError("Unable to discard staged object") from exc
            finally:
                self._path = None


class LocalStorageProvider(StorageProvider):
    """Private filesystem storage whose callers only handle opaque object keys."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_key(self, storage_key: str) -> Path:
        if not storage_key or "\\" in storage_key or "\x00" in storage_key:
            raise InvalidStorageKeyError("Invalid storage key")
        key = PurePosixPath(storage_key)
        if key.is_absolute() or any(part in {"", ".", ".."} for part in key.parts):
            raise InvalidStorageKeyError("Invalid storage key")
        candidate = self.root.joinpath(*key.parts).resolve(strict=False)
        if not candidate.is_relative_to(self.root) or candidate == self.root:
            raise InvalidStorageKeyError("Storage key escapes configured root")
        return candidate

    def stage(self) -> LocalStagedWrite:
        try:
            return LocalStagedWrite(self)
        except OSError as exc:
            raise StorageError("Unable to create staged object") from exc

    def open(self, storage_key: str) -> BinaryIO:
        try:
            return self.resolve_key(storage_key).open("rb")
        except InvalidStorageKeyError:
            raise
        except OSError as exc:
            raise StorageError("Stored object is unavailable") from exc

    def exists(self, storage_key: str) -> bool:
        return self.resolve_key(storage_key).is_file()

    def size(self, storage_key: str) -> int:
        try:
            return self.resolve_key(storage_key).stat().st_size
        except InvalidStorageKeyError:
            raise
        except OSError as exc:
            raise StorageError("Stored object is unavailable") from exc

    def delete(self, storage_key: str) -> None:
        try:
            self.resolve_key(storage_key).unlink(missing_ok=True)
        except InvalidStorageKeyError:
            raise
        except OSError as exc:
            raise StorageError("Unable to remove stored object") from exc

    def put(self, storage_key: str, data: bytes) -> None:
        staged = self.stage()
        try:
            staged.write(data)
            staged.commit(storage_key)
        finally:
            staged.discard()

    def get(self, storage_key: str) -> bytes:
        with self.open(storage_key) as stored:
            return stored.read()
