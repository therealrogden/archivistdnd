"""Tests for summary whitespace normalization."""

from archivist_mcp.summary_text import normalize_for_summary_guard


def test_normalize_for_summary_guard_trailing_newlines_and_whitespace() -> None:
    assert normalize_for_summary_guard("hello\n") == normalize_for_summary_guard("hello")
    assert normalize_for_summary_guard("  a  \n  b  \n") == "  a\n  b"
