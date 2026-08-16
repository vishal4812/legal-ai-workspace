from __future__ import annotations

import re

from app.documents.extractors.base import ExtractedDocument

HORIZONTAL_WHITESPACE = re.compile(r"[ \t\f\v]+")
EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(value: str) -> str:
    """Remove mechanical parser noise without changing words or punctuation."""

    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in value.split("\n")]
    return EXCESS_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def render_extracted_text(extracted: ExtractedDocument) -> str:
    """Create stable persisted text while retaining recoverable PDF pages."""

    normalized_pages = [
        (page.page_number, normalize_text(page.text)) for page in extracted.pages
    ]
    if not any(text for _, text in normalized_pages):
        return ""
    if extracted.page_count is None:
        return normalize_text("\n\n".join(text for _, text in normalized_pages))

    sections = [
        f"[Page {page_number}]" + (f"\n\n{text}" if text else "")
        for page_number, text in normalized_pages
    ]
    return "\n\n".join(sections)
