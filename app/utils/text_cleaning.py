"""Text cleaning helpers used during PDF ingestion.

PDF extraction is notoriously noisy: hyphenated line breaks, stray form-feed
characters, repeated whitespace, and non-printable artifacts. Normalising the
text before chunking improves both embedding quality and the readability of
retrieved context.
"""

from __future__ import annotations

import re

# Pre-compiled patterns (compiled once at import time for efficiency).
_HYPHENATED_LINEBREAK = re.compile(r"(\w)-\n(\w)")
_MULTIPLE_NEWLINES = re.compile(r"\n{3,}")
_WHITESPACE = re.compile(r"[ \t\f\v]+")
_NON_PRINTABLE = re.compile(r"[^\x09\x0a\x0d\x20-\x7e -￿]")


def clean_text(text: str) -> str:
    """Normalise raw text extracted from a PDF page.

    Steps:
        1. Re-join words split across lines by a trailing hyphen.
        2. Strip non-printable / control characters.
        3. Collapse runs of spaces/tabs into a single space.
        4. Collapse excessive blank lines.
        5. Trim leading/trailing whitespace.

    Args:
        text: Raw extracted text.

    Returns:
        Cleaned text (may be an empty string if the page had no real content).
    """
    if not text:
        return ""

    text = _HYPHENATED_LINEBREAK.sub(r"\1\2", text)
    text = _NON_PRINTABLE.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    text = _MULTIPLE_NEWLINES.sub("\n\n", text)
    # Strip trailing spaces on each line.
    text = "\n".join(line.strip() for line in text.splitlines())
    return text.strip()
