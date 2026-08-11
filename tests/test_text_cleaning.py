"""Unit tests for the text-cleaning utility (no external dependencies)."""

from app.utils.text_cleaning import clean_text


def test_rejoins_hyphenated_linebreaks():
    # Unix line endings
    assert clean_text("inter-\nnational") == "international"
    # Windows line endings (CRLF)
    assert clean_text("multi-\r\ntenant") == "multitenant"
    # Hyphen with trailing spaces
    assert clean_text("cooperation-  \r\n  rules") == "cooperationrules"


def test_collapses_whitespace():
    assert clean_text("hello     world\t\tagain") == "hello world again"


def test_collapses_excess_blank_lines():
    cleaned = clean_text("a\n\n\n\n\nb")
    assert cleaned == "a\n\nb"


def test_strips_invisible_unicode_and_keeps_bmp():
    # BOM (\ufeff), Zero-width space (\u200b), soft hyphen (\u00ad)
    assert clean_text("hello\u200bworld\ufeffagain\u00ad") == "helloworldagain"
    # Standard characters (accented characters, CJK) should be preserved
    assert clean_text("Café in 東京") == "Café in 東京"


def test_empty_input_returns_empty_string():
    assert clean_text("") == ""
    assert clean_text("   \n  \n ") == ""
