"""Tool-level errors that are not raw HTTP upstream failures."""

from __future__ import annotations

from typing import Any

from .client import ArchivistUpstreamError


class CommitPartialFailureError(Exception):
    """Archive journal succeeded but the primary PATCH failed (DESIGN.md partial-failure reporting)."""

    def __init__(
        self,
        *,
        message: str,
        orphan: dict[str, Any],
        patch_error: ArchivistUpstreamError,
    ) -> None:
        super().__init__(message)
        self.orphan = orphan
        self.patch_error = patch_error
