"""Text cleaning helpers used during PDF ingestion.

PDF extraction is notoriously noisy: hyphenated line breaks, stray form-feed
characters, repeated whitespace, invisible Unicode junk, and non-printable
artifacts. Normalising the text before chunking improves both embedding
quality and the readability of retrieved context.
"""

from __future__ import annotations

import re

# Pre-compiled patterns (compiled once at import time for efficiency).

# Joins words split across a line break by a trailing hyphen, e.g.
# "informa-\ntion" -> "information". Tolerates trailing spaces and both
# Unix (\n) and Windows (\r\n) line endings.
_HYPHENATED_LINEBREAK = re.compile(r"(\w)-[ \t]*\r?\n[ \t]*(\w)")

_MULTIPLE_NEWLINES = re.compile(r"\n{3,}")
_WHITESPACE = re.compile(r"[ \t\f\v]+")

# Strips control characters (keeping tab/LF/CR) and anything outside the
# Basic Multilingual Plane (rare CJK extensions, emoji via surrogate pairs).
_NON_PRINTABLE = re.compile(r"[^\x09\x0a\x0d\x20-\uffff]")

# Invisible Unicode characters that commonly leak out of PDF text layers and
# silently pollute embeddings: zero-width spaces/joiners, bidi control
# characters, byte-order mark, and soft hyphen.
_INVISIBLE_UNICODE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff\u00ad]")


def clean_text(text: str) -> str:
    """Normalise raw text extracted from a PDF page.

    Steps:
        1. Re-join words split across lines by a trailing hyphen (handles
           both \\n and \\r\\n line endings).
        2. Strip non-printable / control characters.
        3. Strip invisible Unicode junk (zero-width spaces, BOM, etc.).
        4. Collapse runs of spaces/tabs into a single space.
        5. Collapse excessive blank lines.
        6. Trim leading/trailing whitespace.

    Args:
        text: Raw extracted text.

    Returns:
        Cleaned text (may be an empty string if the page had no real content).
    """
    if not text:
        return ""

    text = _HYPHENATED_LINEBREAK.sub(r"\1\2", text)
    text = _NON_PRINTABLE.sub("", text)
    text = _INVISIBLE_UNICODE.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    text = _MULTIPLE_NEWLINES.sub("\n\n", text)
    # Strip trailing spaces on each line.
    text = "\n".join(line.strip() for line in text.splitlines())
    return text.strip()
    