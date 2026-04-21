"""Campaign summary draft/commit tools (DESIGN.md step 12)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from ..api_lists import fetch_all_list_pages
from ..client import ArchivistUpstreamError
from ..errors import CommitPartialFailureError
from ..journal_folders import ensure_journal_folder_path
from ..logging_ import emit_commit_partial_failure, get_logger
from ..server import client, config, mcp
from ..summary_text import is_nonempty_summary, normalize_for_summary_guard
from ..validation import ContentStr
from .journals import find_journal_by_folder_and_title

OVERVIEW_JOURNAL_TITLE = "Campaign Overview"

_ENTITY_GET: dict[str, tuple[str, str]] = {
    "character": ("/v1/characters/", "name"),
    "item": ("/v1/items/", "name"),
    "faction": ("/v1/factions/", "name"),
    "location": ("/v1/locations/", "name"),
    "quest": ("/v1/quests/", "name"),
    "journal": ("/v1/journals/", "title"),
}


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


def _session_sort_key(s: dict[str, Any]) -> str:
    return str(s.get("session_date") or s.get("title") or "")


async def _resolve_link_entity_label(entity_type: str, entity_id: str) -> str:
    t = entity_type.lower()
    pair = _ENTITY_GET.get(t)
    if not pair:
        return entity_id
    prefix, name_key = pair
    try:
        row = await client.get(f"{prefix}{entity_id}")
    except ArchivistUpstreamError:
        return entity_id
    name = row.get(name_key)
    return str(name) if name else entity_id


@mcp.tool
async def draft_campaign_summary(guidance: str | None = None) -> dict[str, Any]:
    """Aggregate campaign description, session summaries, quests, and hub entities (read-only)."""
    campaign = await client.get(f"/v1/campaigns/{client.campaign_id}")
    sessions = await fetch_all_list_pages(client, "/v1/sessions", campaign_id=client.campaign_id)
    sessions_sorted = sorted(sessions, key=_session_sort_key)
    session_blocks: list[str] = []
    for s in sessions_sorted:
        sid = s.get("id")
        if not isinstance(sid, str):
            continue
        detail = await client.get(f"/v1/sessions/{sid}")
        title = detail.get("title") or sid
        summ = detail.get("summary")
        summ_s = summ if isinstance(summ, str) else ""
        excerpt = summ_s if len(summ_s) <= 400 else summ_s[:400] + "…"
        session_blocks.append(f"### {title}\n{excerpt or '_No summary._'}\n")
    quests = await fetch_all_list_pages(client, "/v1/quests", campaign_id=client.campaign_id)
    quest_lines = []
    for q in quests:
        quest_lines.append(f"- {q.get('name', q.get('id'))} ({q.get('status', '')})")
    links = await fetch_all_list_pages(
        client,
        f"/v1/campaigns/{client.campaign_id}/links",
    )
    degree: dict[tuple[str, str], int] = {}
    for link in links:
        for key_pair in (
            (link.get("from_type"), link.get("from_id")),
            (link.get("to_type"), link.get("to_id")),
        ):
            et, eid = key_pair
            if isinstance(et, str) and isinstance(eid, str):
                k = (et.lower(), eid)
                degree[k] = degree.get(k, 0) + 1
    top = sorted(degree.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))[:5]
    hub_lines: list[str] = []
    for (et, eid), _cnt in top:
        label = await _resolve_link_entity_label(et, eid)
        hub_lines.append(f"- {et}: {label} (`{eid}`)")
    lines: list[str] = []
    lines.append("# Draft campaign summary")
    if guidance:
        lines.append(f"*Guidance:* {guidance}")
    lines.append("")
    lines.append("## Current description")
    desc = campaign.get("description")
    lines.append(desc if isinstance(desc, str) else "_None_")
    lines.append("")
    lines.append("## Sessions (chronological)")
    lines.extend(session_blocks or ["_No sessions._"])
    lines.append("## Quests")
    lines.extend(quest_lines or ["_No quests._"])
    lines.append("## Linked entities (hub sample)")
    lines.extend(hub_lines or ["_No links._"])
    lines.append("")
    lines.append("## Draft body")
    lines.append("_Edit the long-form campaign text here._")
    return {
        "campaign_id": client.campaign_id,
        "campaign_title": campaign.get("title"),
        "prior_description": campaign.get("description") if isinstance(campaign.get("description"), str) else "",
        "draft_markdown": "\n".join(lines),
    }


@mcp.tool
async def commit_campaign_summary(
    target: Literal["description", "overview"],
    content: ContentStr,
) -> dict[str, Any]:
    """Commit campaign description or the pinned Campaign Overview journal (equality-guarded, archive-first)."""
    if target == "description":
        campaign = await client.get(f"/v1/campaigns/{client.campaign_id}")
        cur = campaign.get("description")
        cur_s = cur if isinstance(cur, str) else ""
        if normalize_for_summary_guard(cur_s) == normalize_for_summary_guard(content):
            return {"already_current": True, "target": target, "campaign_id": client.campaign_id}
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
                    json={"description": content},
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
                "target": target,
                "prior_description": cur_s,
                "campaign": updated,
                "archived_journal_id": journal_id,
            }
        updated = await client.patch(
            f"/v1/campaigns/{client.campaign_id}",
            json={"description": content},
        )
        return {
            "target": target,
            "prior_description": cur_s,
            "campaign": updated,
            "archived_journal_id": None,
        }

    overview_folder_id = await ensure_journal_folder_path(client, config.overview_folder)
    existing_id, current_content = await find_journal_by_folder_and_title(
        folder_id=overview_folder_id,
        title=OVERVIEW_JOURNAL_TITLE,
    )
    cur_ov = current_content if isinstance(current_content, str) else ""
    if normalize_for_summary_guard(cur_ov) == normalize_for_summary_guard(content):
        return {"already_current": True, "target": target, "campaign_id": client.campaign_id}
    if is_nonempty_summary(cur_ov):
        history_folder_id = await ensure_journal_folder_path(client, config.history_folder)
        iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        archive_title = f"Campaign Overview — superseded {iso}"
        archive_payload: dict[str, Any] = {
            "campaign_id": client.campaign_id,
            "folder_id": history_folder_id,
            "title": archive_title,
            "content": cur_ov,
            "tags": ["summary-history", "campaign"],
            "status": "published",
        }
        archive_resp = await client.post("/v1/journals", json=archive_payload)
        journal_id = _journal_create_id(archive_resp)
        if not journal_id:
            raise RuntimeError(f"archive journal create missing id: {archive_resp!r}")
        try:
            if existing_id:
                updated_body = await client.put(
                    "/v1/journals",
                    json={
                        "id": existing_id,
                        "title": OVERVIEW_JOURNAL_TITLE,
                        "content": content,
                        "tags": ["campaign-overview"],
                        "status": "published",
                    },
                )
            else:
                updated_body = await client.post(
                    "/v1/journals",
                    json={
                        "campaign_id": client.campaign_id,
                        "folder_id": overview_folder_id,
                        "title": OVERVIEW_JOURNAL_TITLE,
                        "content": content,
                        "tags": ["campaign-overview"],
                        "status": "published",
                    },
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
                message="Campaign overview archive succeeded but journal write failed.",
                orphan={
                    "folder_id": history_folder_id,
                    "title": archive_title,
                    "journal_id": journal_id,
                },
                patch_error=exc,
            ) from exc
        jid = existing_id
        if not existing_id and isinstance(updated_body, dict):
            jid = updated_body.get("id") or _journal_create_id(updated_body)
        return {
            "target": target,
            "prior_overview": cur_ov,
            "journal_id": jid,
            "archived_journal_id": journal_id,
        }

    if existing_id:
        updated_body = await client.put(
            "/v1/journals",
            json={
                "id": existing_id,
                "title": OVERVIEW_JOURNAL_TITLE,
                "content": content,
                "tags": ["campaign-overview"],
                "status": "published",
            },
        )
        return {
            "target": target,
            "prior_overview": cur_ov,
            "journal_id": existing_id,
            "archived_journal_id": None,
            "response": updated_body,
        }
    created = await client.post(
        "/v1/journals",
        json={
            "campaign_id": client.campaign_id,
            "folder_id": overview_folder_id,
            "title": OVERVIEW_JOURNAL_TITLE,
            "content": content,
            "tags": ["campaign-overview"],
            "status": "published",
        },
    )
    new_id = _journal_create_id(created)
    return {
        "target": target,
        "prior_overview": cur_ov,
        "journal_id": new_id,
        "archived_journal_id": None,
        "response": created,
    }
