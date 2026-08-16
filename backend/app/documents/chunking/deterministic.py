from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass

from app.documents.chunking.base import Chunk, Chunker

TOKEN_PATTERN = re.compile(r"\S+")
PAGE_MARKER_PATTERN = re.compile(r"(?m)^\[Page ([1-9][0-9]*)\][ \t]*$")
PARAGRAPH_BOUNDARY_PATTERN = re.compile(r"\n[ \t]*\n+")
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?;:])(?:[ \t]+|\n)")


@dataclass(frozen=True, slots=True)
class _Token:
    start: int
    end: int


class DeterministicLegalChunker(Chunker):
    """Split exact normalized text using stable structural and word boundaries.

    A non-whitespace lexeme is the deterministic token approximation. Target size is
    a soft upper bound: paragraph/sentence endings are preferred, and a short final
    fragment is merged into the previous chunk so legal content is never discarded.
    """

    def __init__(self, chunk_size: int, overlap: int, minimum_size: int) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be non-negative and smaller than chunk_size")
        if minimum_size < 1 or minimum_size > chunk_size:
            raise ValueError("minimum_size must be between 1 and chunk_size")
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._minimum_size = minimum_size

    def chunk(self, text: str) -> list[Chunk]:
        if not text or not text.strip():
            return []

        tokens = [_Token(match.start(), match.end()) for match in TOKEN_PATTERN.finditer(text)]
        if not tokens:
            return []

        preferred_offsets = self._preferred_offsets(text)
        ranges: list[tuple[int, int]] = []
        start_token = 0
        while start_token < len(tokens):
            remaining = len(tokens) - start_token
            if remaining <= self._chunk_size:
                ranges.append((start_token, len(tokens)))
                break

            hard_end = start_token + self._chunk_size
            minimum_end = min(start_token + self._minimum_size, hard_end)
            end_token = self._preferred_end(
                tokens,
                preferred_offsets,
                minimum_end,
                hard_end,
            )
            if end_token <= start_token:
                end_token = hard_end
            ranges.append((start_token, end_token))
            next_start = max(end_token - self._overlap, start_token + 1)
            start_token = next_start

        if len(ranges) > 1:
            final_start, final_end = ranges[-1]
            if final_end - final_start < self._minimum_size:
                previous_start, _ = ranges[-2]
                ranges[-2] = (previous_start, final_end)
                ranges.pop()

        markers = [
            (match.start(), int(match.group(1)))
            for match in PAGE_MARKER_PATTERN.finditer(text)
        ]
        chunks: list[Chunk] = []
        for index, (token_start, token_end) in enumerate(ranges):
            start_offset = tokens[token_start].start
            end_offset = tokens[token_end - 1].end
            content = text[start_offset:end_offset]
            page_start, page_end = self._page_range(markers, start_offset, end_offset)
            chunks.append(
                Chunk(
                    index=index,
                    content=content,
                    token_count=token_end - token_start,
                    page_start=page_start,
                    page_end=page_end,
                )
            )
        return chunks

    @staticmethod
    def _preferred_offsets(text: str) -> tuple[int, ...]:
        offsets = {match.end() for match in PARAGRAPH_BOUNDARY_PATTERN.finditer(text)}
        offsets.update(match.end() for match in SENTENCE_BOUNDARY_PATTERN.finditer(text))
        offsets.update(match.start() for match in PAGE_MARKER_PATTERN.finditer(text))
        return tuple(sorted(offsets))

    @staticmethod
    def _preferred_end(
        tokens: list[_Token],
        offsets: tuple[int, ...],
        minimum_end: int,
        hard_end: int,
    ) -> int:
        for candidate in range(hard_end, minimum_end - 1, -1):
            token_end = tokens[candidate - 1].end
            next_start = tokens[candidate].start if candidate < len(tokens) else token_end
            offset_index = bisect_left(offsets, token_end)
            if offset_index < len(offsets) and offsets[offset_index] <= next_start:
                return candidate
        return hard_end

    @staticmethod
    def _page_range(
        markers: list[tuple[int, int]], start_offset: int, end_offset: int
    ) -> tuple[int | None, int | None]:
        if not markers:
            return None, None
        pages = [page for offset, page in markers if offset < end_offset]
        if not pages:
            return None, None
        start_candidates = [page for offset, page in markers if offset <= start_offset]
        page_start = start_candidates[-1] if start_candidates else pages[0]
        return page_start, pages[-1]
