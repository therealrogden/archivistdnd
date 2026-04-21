"""Campaign entity graph links (DESIGN.md step 15)."""

from __future__ import annotations

from typing import Any

from ..api_lists import fetch_all_list_pages
from ..server import client, mcp
from ..validation import AliasStr, UuidPathStr


def _norm(s: str) -> str:
    return str(s).strip().lower()


def _wire_entity_type(s: str) -> str:
    """Archivist link types use Title Case (e.g. ``Character``)."""
    t = str(s).strip().replace("_", " ")
    parts = [p[:1].upper() + p[1:].lower() if p else "" for p in t.split()]
    return " ".join(parts) if " " in t else (t[:1].upper() + t[1:].lower() if t else t)


def _link_tuple(link: dict[str, Any]) -> tuple[str, str, str, str] | None:
    fi = link.get("from_id")
    ft = link.get("from_type")
    ti = link.get("to_id")
    tt = link.get("to_type")
    if not all(isinstance(x, str) for x in (fi, ft, ti, tt)):
        return None
    return (_norm(fi), _norm(ft), _norm(ti), _norm(tt))


@mcp.tool
async def link_entities(
    from_id: UuidPathStr,
    from_type: str,
    to_id: UuidPathStr,
    to_type: str,
    alias: AliasStr | None = None,
) -> dict[str, Any]:
    """Create a campaign link, or return an existing one keyed by ``(from_id, from_type, to_id, to_type)``."""
    want = (_norm(from_id), _norm(from_type), _norm(to_id), _norm(to_type))
    links = await fetch_all_list_pages(client, f"/v1/campaigns/{client.campaign_id}/links")
    for link in links:
        tup = _link_tuple(link)
        if tup == want:
            lid = link.get("id")
            out_link = dict(link)
            if isinstance(lid, str) and alias is not None:
                await client.patch(
                    f"/v1/campaigns/{client.campaign_id}/links/{lid}",
                    json={"alias": alias},
                )
                out_link["alias"] = alias
            return {"already_exists": True, "link": out_link, "link_id": out_link.get("id")}
    body: dict[str, Any] = {
        "from_id": from_id,
        "from_type": _wire_entity_type(from_type),
        "to_id": to_id,
        "to_type": _wire_entity_type(to_type),
    }
    if alias is not None:
        body["alias"] = alias
    created = await client.post(f"/v1/campaigns/{client.campaign_id}/links", json=body)
    lid = created.get("id") if isinstance(created, dict) else None
    return {"already_exists": False, "link": created, "link_id": lid}
