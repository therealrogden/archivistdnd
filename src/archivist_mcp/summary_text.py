"""Whitespace normalization for summary equality guards (DESIGN.md Idempotency)."""

from __future__ import annotations


def normalize_for_summary_guard(text: str | None) -> str:
    """Normalize summary text for equality comparison.

    - Treat ``None`` as empty.
    - Normalize newlines to ``\\n``.
    - Strip trailing whitespace from each line.
    - Strip leading / trailing blank lines from the whole string.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        return ""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def is_nonempty_summary(text: str | None) -> bool:
    """True when the summary should trigger an archive-before-overwrite."""
    return bool(normalize_for_summary_guard(text))
