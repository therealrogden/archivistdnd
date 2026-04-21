"""Compendium item registration and mechanics promotion (DESIGN.md step 14)."""

from __future__ import annotations

import json
from typing import Any

from ..api_lists import fetch_all_list_pages
from ..journal_folders import ensure_journal_folder_path
from ..server import client, config, mcp
from ..validation import (
    ContentStr,
    ItemType,
    MechanicsDict,
    ShortNameStr,
    TagsList,
    UuidPathStr,
    mechanics_signature,
    parse_item_type,
)
from .journals import find_journal_by_folder_and_title


def _mechanics_journal_title(item_name: str) -> str:
    return f"{item_name} — Mechanics"


def _mechanics_wikilink(item_name: str) -> str:
    return f"[[{_mechanics_journal_title(item_name)}]]"


def _mechanics_journal_markdown(item_name: str, mechanics: dict[str, Any], item_type: ItemType) -> str:
    rarity = mechanics.get("rarity", "—")
    att = mechanics.get("attunement", "—")
    header = f"*Type · Rarity · Attunement*\n\n{item_type.value.title()} · {rarity} · {att}"
    rows: list[str] = []
    for key in ("damage", "properties", "mastery", "weight"):
        if key in mechanics:
            rows.append(f"| {key.replace('_', ' ').title()} | {mechanics[key]} |")
    table = ""
    if rows:
        table = "\n| Property | Value |\n|---|---|\n" + "\n".join(rows) + "\n"
    notes = mechanics.get("notes", "")
    return (
        f"# {item_name}\n\n{header}\n{table}\n"
        f"## Lore\nLinked to [[{item_name}]] — see narrative entry for story context.\n\n"
        f"## Mechanical notes\n{notes if isinstance(notes, str) else json.dumps(notes, ensure_ascii=False)}\n"
    )


def _append_mechanics_line(description: str, item_name: str) -> str:
    suffix = f"\n\nSee mechanics: {_mechanics_wikilink(item_name)}"
    if suffix.strip() in description:
        return description
    return (description.rstrip() + suffix).strip()


@mcp.tool
async def register_item(
    name: ShortNameStr,
    description: ContentStr,
    mechanics: MechanicsDict | None = None,
    item_type: ItemType | str = ItemType.WEAPON,
    image: str | None = None,
    tags: TagsList | None = None,
) -> dict[str, Any]:
    """Create a campaign item; optional mechanics dict creates a paired statblock journal."""
    itype = parse_item_type(item_type)
    mech_dict = mechanics
    if mech_dict is not None:
        want_sig = mechanics_signature(mech_dict)
        items = await fetch_all_list_pages(client, "/v1/items", campaign_id=client.campaign_id)
        for row in items:
            if row.get("name") != name:
                continue
            raw_m = row.get("mechanics")
            if not isinstance(raw_m, dict):
                continue
            if mechanics_signature(raw_m) == want_sig:
                detail = await client.get(f"/v1/items/{row['id']}")
                return {"already_exists": True, "item": detail}
    post: dict[str, Any] = {
        "name": name,
        "campaign_id": client.campaign_id,
        "description": description,
        "type": itype.value,
    }
    if mech_dict is not None:
        post["mechanics"] = mech_dict
    if image is not None:
        post["image"] = image
    created = await client.post("/v1/items", json=post)
    item_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(item_id, str):
        raise RuntimeError(f"item create missing id: {created!r}")
    item = await client.get(f"/v1/items/{item_id}")
    if mech_dict is None:
        return {"already_exists": False, "item": item}
    folder_id = await ensure_journal_folder_path(client, config.mechanics_folder)
    jtitle = _mechanics_journal_title(name)
    md = _mechanics_journal_markdown(name, mech_dict, itype)
    caller_tags = list(tags) if tags is not None else []
    auto_tags = ["mechanics", itype.value.lower()]
    journal_tags = list(dict.fromkeys(caller_tags + auto_tags))
    journal_body = {
        "campaign_id": client.campaign_id,
        "folder_id": folder_id,
        "title": jtitle,
        "content": md,
        "tags": journal_tags,
        "status": "published",
    }
    jr = await client.post("/v1/journals", json=journal_body)
    jid = jr.get("id") if isinstance(jr, dict) else None
    if not isinstance(jid, str):
        inner = jr.get("data") if isinstance(jr, dict) else None
        if isinstance(inner, dict) and isinstance(inner.get("id"), str):
            jid = inner["id"]
    if not isinstance(jid, str):
        raise RuntimeError(f"journal create missing id: {jr!r}")
    new_desc = _append_mechanics_line(item.get("description") or description, name)
    updated = await client.patch(
        f"/v1/items/{item_id}",
        json={"description": new_desc},
    )
    return {"already_exists": False, "item": updated, "mechanics_journal_id": jid}


@mcp.tool
async def promote_item_to_homebrew(
    item_id: UuidPathStr,
    mechanics: MechanicsDict,
) -> dict[str, Any]:
    """Add a mechanics statblock journal to an existing item and wikilink it from the description."""
    item = await client.get(f"/v1/items/{item_id}")
    iname = item.get("name")
    if not isinstance(iname, str):
        raise ValueError("item has no name")
    itype = parse_item_type(item.get("type", "weapon"))
    folder_id = await ensure_journal_folder_path(client, config.mechanics_folder)
    jtitle = _mechanics_journal_title(iname)
    md = _mechanics_journal_markdown(iname, mechanics, itype)
    existing_id, _ = await find_journal_by_folder_and_title(folder_id=folder_id, title=jtitle)
    if existing_id:
        await client.put(
            "/v1/journals",
            json={
                "id": existing_id,
                "title": jtitle,
                "content": md,
                "tags": ["mechanics", itype.value.lower()],
                "status": "published",
            },
        )
        jid = existing_id
    else:
        jr = await client.post(
            "/v1/journals",
            json={
                "campaign_id": client.campaign_id,
                "folder_id": folder_id,
                "title": jtitle,
                "content": md,
                "tags": ["mechanics", itype.value.lower()],
                "status": "published",
            },
        )
        jid = jr.get("id") if isinstance(jr, dict) else None
        if not isinstance(jid, str):
            inner = jr.get("data") if isinstance(jr, dict) else None
            if isinstance(inner, dict) and isinstance(inner.get("id"), str):
                jid = inner["id"]
        if not isinstance(jid, str):
            raise RuntimeError(f"journal create missing id: {jr!r}")
    desc = item.get("description") if isinstance(item.get("description"), str) else ""
    new_desc = _append_mechanics_line(desc, iname)
    updated = await client.patch(
        f"/v1/items/{item_id}",
        json={"description": new_desc},
    )
    return {"item": updated, "mechanics_journal_id": jid}
