"""Campaign description commit (DESIGN.md step 12)."""

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
from ..validation import ContentStr
from .wikilinks import strip_unresolved_wikilinks


def _archive_campaign_title(*, when: datetime) -> str:
    iso = when.strftime("%Y-%m-%dT%H:%MZ")
    return f"Campaign description — superseded {iso}"


def _journal_create_id(body: Any) -> str | None:
    if isinstance(body, dict):
        if isinstance(body.get("id"), str):
            return body["id"]
        inner = body.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("id"), str):
            return inner["id"]
    return None


@mcp.tool
async def commit_campaign_summary(content: ContentStr) -> dict[str, Any]:
    """Archive prior non-empty description to Summary History, then PATCH the campaign (wikilinks stripped when unresolved)."""
    campaign = await client.get(f"/v1/campaigns/{client.campaign_id}")
    cur = campaign.get("description")
    cur_s = cur if isinstance(cur, str) else ""

    stripped, stripped_log = await strip_unresolved_wikilinks(client, client.campaign_id, content)
    if normalize_for_summary_guard(cur_s) == normalize_for_summary_guard(stripped):
        return {
            "already_current": True,
            "campaign_id": client.campaign_id,
            "wikilinks_stripped": stripped_log,
        }

    if is_nonempty_summary(cur_s):
        when = datetime.now(timezone.utc)
        history_folder_id = await ensure_journal_folder_path(client, config.history_folder)
        archive_title = _archive_campaign_title(when=when)
        archive_payload: dict[str, Any] = {
            "campaign_id": client.campaign_id,
            "folder_id": history_folder_id,
            "title": archive_title,
            "content": cur_s,
            "tags": ["summary-history", "campaign"],
            "status": "published",
        }
        archive_resp = await client.post("/v1/journals", json=archive_payload)
        journal_id = _journal_create_id(archive_resp)
        if not journal_id:
            raise RuntimeError(f"archive journal create missing id: {archive_resp!r}")
        try:
            updated = await client.patch(
                f"/v1/campaigns/{client.campaign_id}",
                json={"description": stripped},
            )
        except ArchivistUpstreamError as exc:
            emit_commit_partial_failure(
                get_logger("tools.campaign_summary"),
                tool="commit_campaign_summary",
                folder_id=history_folder_id,
                title=archive_title,
                journal_id=journal_id,
                patch_status=exc.status_code,
                patch_uri=exc.uri,
                correlation_id=exc.correlation_id,
                level=logging.WARNING,
            )
            raise CommitPartialFailureError(
                message="Campaign description archive succeeded but campaign PATCH failed.",
                orphan={
                    "folder_id": history_folder_id,
                    "title": archive_title,
                    "journal_id": journal_id,
                },
                patch_error=exc,
            ) from exc
        return {
            "prior_description": cur_s,
            "campaign": updated,
            "archived_journal_id": journal_id,
            "wikilinks_stripped": stripped_log,
        }

    updated = await client.patch(
        f"/v1/campaigns/{client.campaign_id}",
        json={"description": stripped},
    )
    return {
        "prior_description": cur_s,
        "campaign": updated,
        "archived_journal_id": None,
        "wikilinks_stripped": stripped_log,
    }
