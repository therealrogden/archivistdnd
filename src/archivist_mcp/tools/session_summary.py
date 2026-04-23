"""Session summary commit (DESIGN.md step 11)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..client import ArchivistUpstreamError
from ..errors import CommitPartialFailureError
from ..journal_folders import ensure_journal_folder_path
from ..logging_ import emit_commit_partial_failure, get_logger
from ..server import client, config, mcp
from ..summary_text import is_nonempty_summary, normalize_for_summary_guard
from ..validation import ContentStr, ShortTitleStr, UuidPathStr
from .wikilinks import strip_unresolved_wikilinks


def _archive_title(*, session_title: str, when: datetime) -> str:
    iso = when.strftime("%Y-%m-%dT%H:%MZ")
    return f"{session_title} — superseded {iso}"


def _journal_create_id(body: Any) -> str | None:
    if isinstance(body, dict):
        if isinstance(body.get("id"), str):
            return body["id"]
        inner = body.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("id"), str):
            return inner["id"]
    return None


@mcp.tool
async def commit_session_summary(
    session_id: UuidPathStr,
    summary: ContentStr,
    title: ShortTitleStr | None = None,
) -> dict[str, Any]:
    """Archive prior non-empty summary to Summary History, then PATCH the session (wikilinks stripped when unresolved)."""
    session = await client.get(f"/v1/sessions/{session_id}")
    prior_raw = session.get("summary")
    prior_str = prior_raw if isinstance(prior_raw, str) else ""

    stripped, stripped_log = await strip_unresolved_wikilinks(client, client.campaign_id, summary)
    if normalize_for_summary_guard(prior_str) == normalize_for_summary_guard(stripped):
        return {
            "already_current": True,
            "session_id": session_id,
            "wikilinks_stripped": stripped_log,
        }

    if is_nonempty_summary(prior_str):
        when = datetime.now(timezone.utc)
        history_folder_id = await ensure_journal_folder_path(client, config.history_folder)
        stitle = session.get("title") if isinstance(session.get("title"), str) else "Session"
        archive_title = _archive_title(session_title=stitle, when=when)
        tags = ["summary-history", "session"]
        archive_payload: dict[str, Any] = {
            "campaign_id": client.campaign_id,
            "folder_id": history_folder_id,
            "title": archive_title,
            "content": prior_str,
            "tags": tags,
            "status": "published",
        }
        archive_resp = await client.post("/v1/journals", json=archive_payload)
        journal_id = _journal_create_id(archive_resp)
        if not journal_id:
            raise RuntimeError(f"archive journal create missing id: {archive_resp!r}")
        patch_body: dict[str, Any] = {"summary": stripped}
        if title is not None:
            patch_body["title"] = title
        try:
            updated = await client.patch(f"/v1/sessions/{session_id}", json=patch_body)
        except ArchivistUpstreamError as exc:
            emit_commit_partial_failure(
                get_logger("tools.session_summary"),
                tool="commit_session_summary",
                folder_id=history_folder_id,
                title=archive_title,
                journal_id=journal_id,
                patch_status=exc.status_code,
                patch_uri=exc.uri,
                correlation_id=exc.correlation_id,
                level=logging.WARNING,
            )
            raise CommitPartialFailureError(
                message="Summary archive succeeded but session PATCH failed.",
                orphan={
                    "folder_id": history_folder_id,
                    "title": archive_title,
                    "journal_id": journal_id,
                },
                patch_error=exc,
            ) from exc
        return {
            "session_id": session_id,
            "prior_summary": prior_str,
            "session": updated,
            "archived_journal_id": journal_id,
            "wikilinks_stripped": stripped_log,
        }

    patch_body = {"summary": stripped}
    if title is not None:
        patch_body["title"] = title
    updated = await client.patch(f"/v1/sessions/{session_id}", json=patch_body)
    return {
        "session_id": session_id,
        "prior_summary": prior_str,
        "session": updated,
        "archived_journal_id": None,
        "wikilinks_stripped": stripped_log,
    }
