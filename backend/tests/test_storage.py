from pathlib import Path

import pytest

from app.storage.local import InvalidStorageKeyError, LocalStorageProvider


def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorageProvider(tmp_path)
    storage.put("workspace/case/document.bin", b"private")

    assert storage.get("workspace/case/document.bin") == b"private"

    storage.delete("workspace/case/document.bin")
    assert not (tmp_path / "workspace/case/document.bin").exists()


@pytest.mark.parametrize("key", ["", "/absolute", "../escape", "safe/../../escape"])
def test_local_storage_rejects_unsafe_keys(tmp_path: Path, key: str) -> None:
    storage = LocalStorageProvider(tmp_path)

    with pytest.raises(InvalidStorageKeyError):
        storage.put(key, b"private")
