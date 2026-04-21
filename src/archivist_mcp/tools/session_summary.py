"""Session summary draft/commit tools (DESIGN.md step 11)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..api_lists import list_data
from ..client import ArchivistUpstreamError
from ..errors import CommitPartialFailureError
from ..journal_folders import ensure_journal_folder_path
from ..logging_ import emit_commit_partial_failure, get_logger
from ..server import client, config, mcp
from ..summary_text import is_nonempty_summary, normalize_for_summary_guard
from ..validation import ContentStr, ShortTitleStr, UuidPathStr


def _archive_title(*, session_title: str, when: datetime) -> str:
    iso = when.strftime("%Y-%m-%dT%H:%MZ")
    return f"{session_title} — superseded {iso}"


def _draft_markdown(
    *,
    session: dict[str, Any],
    beats: list[dict[str, Any]],
    moments: list[dict[str, Any]],
    cast_analysis: dict[str, Any] | None,
    style: str | None,
    length: str | None,
) -> str:
    lines: list[str] = []
    title = session.get("title") or "Session"
    lines.append(f"# Draft session summary: {title}")
    if style:
        lines.append(f"*Requested style:* {style}")
    if length:
        lines.append(f"*Requested length:* {length}")
    lines.append("")
    lines.append("## Beats")
    if not beats:
        lines.append("_No beats._")
    else:
        for b in sorted(beats, key=lambda x: (x.get("sequence") is None, x.get("sequence", 0))):
            bt = b.get("title") or b.get("id")
            lines.append(f"- {bt}")
    lines.append("")
    lines.append("## Moments")
    if not moments:
        lines.append("_No moments._")
    else:
        for m in moments:
            excerpt = m.get("content") if isinstance(m.get("content"), str) else ""
            if len(excerpt) > 400:
                excerpt = excerpt[:400] + "…"
            lines.append(f"- {excerpt or m.get('id')}")
    lines.append("")
    if cast_analysis is not None:
        lines.append("## Cast analysis")
        lines.append("```json")
        lines.append(json.dumps(cast_analysis, indent=2, ensure_ascii=False)[:8000])
        lines.append("```")
        lines.append("")
    lines.append("## Draft summary (replace with your narrative)")
    lines.append("_Compose the recap here using the sections above._")
    return "\n".join(lines)


def _journal_create_id(body: Any) -> str | None:
    if isinstance(body, dict):
        if isinstance(body.get("id"), str):
            return body["id"]
        inner = body.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("id"), str):
            return inner["id"]
    return None


@mcp.tool
async def draft_session_summary(
    session_id: UuidPathStr,
    style: str | None = None,
    length: str | None = None,
    include_cast_analysis: bool = False,
) -> dict[str, Any]:
    """Fetch session, beats, moments, and optional cast analysis; return candidate markdown (no writes)."""
    session = await client.get(f"/v1/sessions/{session_id}")
    beats_body = await client.get(
        "/v1/beats",
        campaign_id=client.campaign_id,
        game_session_id=session_id,
        page=1,
        page_size=50,
    )
    beats = list_data(beats_body)
    moments_body = await client.get(
        "/v1/moments",
        campaign_id=client.campaign_id,
        session_id=session_id,
        page=1,
        page_size=50,
    )
    moments = list_data(moments_body)
    cast_analysis: dict[str, Any] | None = None
    if include_cast_analysis:
        try:
            raw = await client.get(f"/v1/sessions/{session_id}/cast-analysis")
            if isinstance(raw, dict):
                cast_analysis = raw
        except ArchivistUpstreamError as exc:
            if exc.status_code != 404:
                raise
    prior = session.get("summary")
    prior_verbatim = prior if isinstance(prior, str) else ""
    draft = _draft_markdown(
        session=session,
        beats=beats,
        moments=moments,
        cast_analysis=cast_analysis,
        style=style,
        length=length,
    )
    return {
        "session_id": session_id,
        "session_title": session.get("title"),
        "prior_summary": prior_verbatim,
        "draft_markdown": draft,
    }


@mcp.tool
async def commit_session_summary(
    session_id: UuidPathStr,
    summary: ContentStr,
    title: ShortTitleStr | None = None,
) -> dict[str, Any]:
    """Archive prior non-empty summary to Summary History, then PATCH the session (equality-guarded)."""
    session = await client.get(f"/v1/sessions/{session_id}")
    prior_raw = session.get("summary")
    prior_str = prior_raw if isinstance(prior_raw, str) else ""
    if normalize_for_summary_guard(prior_str) == normalize_for_summary_guard(summary):
        return {"already_current": True, "session_id": session_id}

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
        patch_body: dict[str, Any] = {"summary": summary}
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
        }

    patch_body = {"summary": summary}
    if title is not None:
        patch_body["title"] = title
    updated = await client.patch(f"/v1/sessions/{session_id}", json=patch_body)
    return {
        "session_id": session_id,
        "prior_summary": prior_str,
        "session": updated,
        "archived_journal_id": None,
    }
