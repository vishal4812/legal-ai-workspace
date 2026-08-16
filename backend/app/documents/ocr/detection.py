from __future__ import annotations

from dataclasses import dataclass

MIN_NON_WHITESPACE_CHARACTERS = 20
MIN_ALPHABETIC_CHARACTERS = 10
MIN_PRINTABLE_RATIO = 0.90
MIN_ALPHANUMERIC_RATIO = 0.50


@dataclass(frozen=True, slots=True)
class TextQuality:
    non_whitespace_characters: int
    alphabetic_characters: int
    printable_ratio: float
    alphanumeric_ratio: float


def measure_text_quality(text: str) -> TextQuality:
    """Measure parser output without attempting to interpret or correct it."""

    normalized = text.replace("\x00", "").strip()
    non_whitespace = [character for character in normalized if not character.isspace()]
    if not non_whitespace:
        return TextQuality(0, 0, 1.0, 0.0)
    printable = sum(character.isprintable() for character in non_whitespace)
    alphabetic = sum(character.isalpha() for character in non_whitespace)
    alphanumeric = sum(character.isalnum() for character in non_whitespace)
    count = len(non_whitespace)
    return TextQuality(
        non_whitespace_characters=count,
        alphabetic_characters=alphabetic,
        printable_ratio=printable / count,
        alphanumeric_ratio=alphanumeric / count,
    )


def is_meaningful_text(text: str) -> bool:
    """Return whether page text is sufficient to avoid OCR.

    A page is direct-text capable only when it has at least 20 non-whitespace
    characters, at least 10 alphabetic characters, at least 90% printable
    characters, and at least 50% alphanumeric characters. This rejects empty
    pages, isolated page numbers/headers, and parser noise deterministically.
    """

    quality = measure_text_quality(text)
    return (
        quality.non_whitespace_characters >= MIN_NON_WHITESPACE_CHARACTERS
        and quality.alphabetic_characters >= MIN_ALPHABETIC_CHARACTERS
        and quality.printable_ratio >= MIN_PRINTABLE_RATIO
        and quality.alphanumeric_ratio >= MIN_ALPHANUMERIC_RATIO
    )
