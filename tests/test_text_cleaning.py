"""Unit tests for the text-cleaning utility (no external dependencies)."""

from app.utils.text_cleaning import clean_text


def test_rejoins_hyphenated_linebreaks():
    assert clean_text("inter-\nnational") == "international"


def test_collapses_whitespace():
    assert clean_text("hello     world\t\tagain") == "hello world again"


def test_collapses_excess_blank_lines():
    cleaned = clean_text("a\n\n\n\n\nb")
    assert cleaned == "a\n\nb"


def test_empty_input_returns_empty_string():
    assert clean_text("") == ""
    assert clean_text("   \n  \n ") == ""
