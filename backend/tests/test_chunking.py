from __future__ import annotations

import hashlib

import pytest

from app.documents.chunking.deterministic import DeterministicLegalChunker


def test_empty_and_short_text_are_deterministic() -> None:
    chunker = DeterministicLegalChunker(20, 4, 5)
    assert chunker.chunk("") == []
    assert chunker.chunk("   \n") == []
    chunks = chunker.chunk("Section 1. Exact legal text, €500.")
    assert len(chunks) == 1
    assert chunks[0].content == "Section 1. Exact legal text, €500."
    assert chunks == chunker.chunk("Section 1. Exact legal text, €500.")


def test_long_text_uses_overlap_order_and_soft_size_bound() -> None:
    text = "\n\n".join(
        f"Section {number}. " + " ".join(f"term-{number}-{word}" for word in range(12))
        for number in range(12)
    )
    chunker = DeterministicLegalChunker(40, 8, 10)
    chunks = chunker.chunk(text)
    assert len(chunks) > 3
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.token_count <= 50 for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        previous_words = previous.content.split()
        current_words = current.content.split()
        assert set(previous_words[-8:]) & set(current_words[:12])
    assert "term-11-11" in chunks[-1].content


def test_page_markers_and_page_ranges_are_preserved() -> None:
    text = (
        "[Page 1]\n\nWHEREAS the first party agrees to all terms.\n\n"
        "[Page 2]\n\nSection 2. Payment is due within thirty days.\n\n"
        "[Page 3]\n\nIN WITNESS WHEREOF the parties execute this Agreement."
    )
    chunks = DeterministicLegalChunker(14, 3, 5).chunk(text)
    combined = "\n".join(chunk.content for chunk in chunks)
    assert "[Page 1]" in combined
    assert "[Page 2]" in combined
    assert "[Page 3]" in combined
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 3
    assert all(
        chunk.page_start is None or chunk.page_start <= (chunk.page_end or chunk.page_start)
        for chunk in chunks
    )


def test_exact_content_hash_can_be_independently_recomputed() -> None:
    content = "[Page 1]\n\nClause 4.2 — amount ₹ 1,234.50; unchanged."
    chunk = DeterministicLegalChunker(50, 5, 5).chunk(content)[0]
    expected = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
    assert expected == hashlib.sha256(content.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "args",
    [(0, 0, 1), (10, 10, 1), (10, -1, 1), (10, 2, 11)],
)
def test_invalid_configuration_is_rejected(args: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        DeterministicLegalChunker(*args)
