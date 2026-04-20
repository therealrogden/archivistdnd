"""Live contract probe for DESIGN.md build-order step 13.

This script probes Archivist API write contracts that are currently modeled as
open questions in the design doc:
1) `Item.type` wire format for multi-word enum values
2) Accepted shape for `mechanics` payload on item creation

Outputs:
- JSON evidence report (full structured data)
- Markdown report (formatted for DESIGN.md Contract Probe Results section)

Usage:
    python scripts/probe_contracts.py
    python scripts/probe_contracts.py --dry-run
    python scripts/probe_contracts.py --output-dir scripts/probe-results
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from archivist_mcp.client import ArchivistClient
from archivist_mcp.config import ConfigError, load_config


MAX_EXCERPT_LEN = 500


@dataclass(frozen=True)
class ProbeCase:
    probe: str
    case_id: str
    description: str
    payload: dict[str, Any]
    is_control: bool = False


@dataclass
class ProbeResult:
    probe: str
    case_id: str
    description: str
    payload: dict[str, Any]
    status_code: int | None
    accepted: bool
    response_excerpt: str
    created_item_id: str | None
    cleanup_attempted: bool
    cleanup_succeeded: bool
    cleanup_error: str | None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _excerpt_from_exception(exc: Exception) -> tuple[int | None, str]:
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text
        return exc.response.status_code, body[:MAX_EXCERPT_LEN]
    return None, f"{type(exc).__name__}: {exc}"


def _case_payload(
    *,
    campaign_id: str,
    name: str,
    description: str,
    item_type: str,
    mechanics: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "campaign_id": campaign_id,
        "name": name,
        "description": description,
        "type": item_type,
    }
    if mechanics is not None:
        payload["mechanics"] = mechanics
    return payload


def build_probe_matrix(campaign_id: str, stamp: str) -> list[ProbeCase]:
    """Return probe cases and controls used to infer contract behavior."""
    base_name = f"probe-step13-{stamp}"
    base_description = "Disposable probe entity for contract validation."

    type_cases = [
        ProbeCase(
            probe="item_type_wire_format",
            case_id="control_weapon",
            description="Control value expected to be accepted.",
            is_control=True,
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-control-weapon",
                description=base_description,
                item_type="weapon",
            ),
        ),
        ProbeCase(
            probe="item_type_wire_format",
            case_id="wondrous_item_space",
            description='Probe type wire format as "wondrous item".',
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-type-space",
                description=base_description,
                item_type="wondrous item",
            ),
        ),
        ProbeCase(
            probe="item_type_wire_format",
            case_id="wondrous_item_underscore",
            description='Probe type wire format as "wondrous_item".',
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-type-underscore",
                description=base_description,
                item_type="wondrous_item",
            ),
        ),
        ProbeCase(
            probe="item_type_wire_format",
            case_id="wondrous_item_hyphen",
            description='Probe type wire format as "wondrous-item".',
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-type-hyphen",
                description=base_description,
                item_type="wondrous-item",
            ),
        ),
    ]

    typed_mechanics = {
        "damage": "1d8 slashing",
        "properties": ["versatile (1d10)"],
        "mastery": "Sap",
        "attunement": False,
        "rarity": "rare",
        "notes": "Probe typed payload.",
    }
    loose_mechanics = {
        "custom_field": {"nested": [1, 2, 3]},
        "charges": 3,
        "active": True,
        "free_text": "Probe loose payload.",
    }

    mechanics_cases = [
        ProbeCase(
            probe="mechanics_payload_shape",
            case_id="control_no_mechanics",
            description="Control payload without mechanics.",
            is_control=True,
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-control-no-mech",
                description=base_description,
                item_type="weapon",
            ),
        ),
        ProbeCase(
            probe="mechanics_payload_shape",
            case_id="typed_object",
            description="Typed object-like mechanics payload.",
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-mech-typed",
                description=base_description,
                item_type="weapon",
                mechanics=typed_mechanics,
            ),
        ),
        ProbeCase(
            probe="mechanics_payload_shape",
            case_id="loose_object",
            description="Loose object payload with nested keys.",
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-mech-loose",
                description=base_description,
                item_type="weapon",
                mechanics=loose_mechanics,
            ),
        ),
        ProbeCase(
            probe="mechanics_payload_shape",
            case_id="invalid_scalar",
            description="Boundary-invalid mechanics payload as scalar string.",
            payload=_case_payload(
                campaign_id=campaign_id,
                name=f"{base_name}-mech-invalid-scalar",
                description=base_description,
                item_type="weapon",
                mechanics="invalid_scalar_payload",
            ),
        ),
    ]
    return [*type_cases, *mechanics_cases]


async def run_case(client: ArchivistClient, case: ProbeCase, dry_run: bool) -> ProbeResult:
    if dry_run:
        return ProbeResult(
            probe=case.probe,
            case_id=case.case_id,
            description=case.description,
            payload=case.payload,
            status_code=None,
            accepted=False,
            response_excerpt="Dry-run: request not sent.",
            created_item_id=None,
            cleanup_attempted=False,
            cleanup_succeeded=False,
            cleanup_error=None,
        )

    created_item_id: str | None = None
    status_code: int | None = None
    accepted = False
    response_excerpt = ""
    cleanup_attempted = False
    cleanup_succeeded = False
    cleanup_error: str | None = None

    try:
        response = await client.post("/v1/items", json=case.payload)
        accepted = True
        status_code = 200
        response_excerpt = _canonical_json(response)[:MAX_EXCERPT_LEN]
        created_item_id = str(response.get("id")) if isinstance(response, dict) else None
    except Exception as exc:
        status_code, response_excerpt = _excerpt_from_exception(exc)

    if created_item_id:
        cleanup_attempted = True
        try:
            await client.delete(f"/v1/items/{created_item_id}")
            cleanup_succeeded = True
        except Exception as exc:
            cleanup_error = f"{type(exc).__name__}: {exc}"

    return ProbeResult(
        probe=case.probe,
        case_id=case.case_id,
        description=case.description,
        payload=case.payload,
        status_code=status_code,
        accepted=accepted,
        response_excerpt=response_excerpt,
        created_item_id=created_item_id,
        cleanup_attempted=cleanup_attempted,
        cleanup_succeeded=cleanup_succeeded,
        cleanup_error=cleanup_error,
    )


def summarize_probe(results: list[ProbeResult], probe_name: str) -> dict[str, Any]:
    probe_results = [r for r in results if r.probe == probe_name]
    controls = [r for r in probe_results if "control" in r.case_id]
    candidates = [r for r in probe_results if "control" not in r.case_id]
    control_ok = any(r.accepted for r in controls)
    accepted_candidates = [r.case_id for r in candidates if r.accepted]
    return {
        "probe": probe_name,
        "control_ok": control_ok,
        "accepted_candidates": accepted_candidates,
        "status": (
            "inconclusive_control_failure"
            if not control_ok
            else ("accepted_candidates_found" if accepted_candidates else "all_candidates_rejected")
        ),
    }


def validator_decision_text(type_summary: dict[str, Any], mechanics_summary: dict[str, Any]) -> str:
    type_decision = (
        f"Accepted Item.type candidates: {type_summary['accepted_candidates']}"
        if type_summary["control_ok"]
        else "Item.type probe inconclusive due to control failure."
    )
    mech_decision = (
        f"Accepted mechanics payload cases: {mechanics_summary['accepted_candidates']}"
        if mechanics_summary["control_ok"]
        else "Mechanics probe inconclusive due to control failure."
    )
    return f"{type_decision} {mech_decision}"


def to_markdown(
    *,
    timestamp: str,
    report_name: str,
    results: list[ProbeResult],
    type_summary: dict[str, Any],
    mechanics_summary: dict[str, Any],
    campaign_id: str,
) -> str:
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    lines: list[str] = [
        "# Contract Probe Report",
        "",
        f"- Date: {date_str}",
        f"- Campaign: {campaign_id}",
        f"- Report ID: {report_name}",
        "",
        "## Probe: Item.type wire format (Open Question #2)",
        "",
        "### Tested payloads",
    ]
    for result in [r for r in results if r.probe == "item_type_wire_format"]:
        lines.append(f"- `{result.case_id}`: `{_canonical_json(result.payload)}`")
    lines.extend(
        [
            "",
            "### Upstream responses",
        ]
    )
    for result in [r for r in results if r.probe == "item_type_wire_format"]:
        lines.append(
            f"- `{result.case_id}` -> HTTP {result.status_code}, accepted={result.accepted}, "
            f"body: `{result.response_excerpt}`"
        )
    lines.extend(
        [
            "",
            f"### Accepted wire format / shape",
            f"- Summary status: `{type_summary['status']}`",
            f"- Accepted candidates: `{type_summary['accepted_candidates']}`",
            "",
            "### Validator decision",
            f"- {validator_decision_text(type_summary, mechanics_summary)}",
            "",
            "## Probe: mechanics payload shape (Open Question #3)",
            "",
            "### Tested payloads",
        ]
    )
    for result in [r for r in results if r.probe == "mechanics_payload_shape"]:
        lines.append(f"- `{result.case_id}`: `{_canonical_json(result.payload)}`")
    lines.extend(["", "### Upstream responses"])
    for result in [r for r in results if r.probe == "mechanics_payload_shape"]:
        lines.append(
            f"- `{result.case_id}` -> HTTP {result.status_code}, accepted={result.accepted}, "
            f"body: `{result.response_excerpt}`"
        )
    lines.extend(
        [
            "",
            "### Accepted wire format / shape",
            f"- Summary status: `{mechanics_summary['status']}`",
            f"- Accepted candidates: `{mechanics_summary['accepted_candidates']}`",
            "",
            "### Cleanup",
        ]
    )
    for result in results:
        if result.created_item_id:
            lines.append(
                f"- `{result.case_id}` created `{result.created_item_id}`; "
                f"cleanup_ok={result.cleanup_succeeded}; cleanup_error={result.cleanup_error}"
            )
    if not any(r.created_item_id for r in results):
        lines.append("- No items created; no cleanup actions required.")
    lines.extend(
        [
            "",
            "### DESIGN.md entry checklist",
            "- Copy tested payloads and responses into the `Contract Probe Results` section.",
            "- Close Open Questions #2 and #3 with links to this report.",
            "- Add validator mapping decisions and commit SHA that locks behavior.",
            "",
            f"_Generated at {timestamp}_",
        ]
    )
    return "\n".join(lines) + "\n"


def write_reports(
    output_dir: Path,
    report_name: str,
    report: dict[str, Any],
    markdown: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report_name}.json"
    md_path = output_dir / f"{report_name}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


async def async_main(args: argparse.Namespace) -> int:
    if args.dry_run:
        try:
            config = load_config()
        except ConfigError:
            # Dry-run still needs a campaign_id for payload shape previews.
            from types import SimpleNamespace

            config = SimpleNamespace(
                campaign_id="dry-run-campaign-id",
                api_key="dry-run",
                base_url="https://api.myarchivist.ai",
            )
    else:
        try:
            config = load_config()
        except ConfigError as exc:
            print(f"[FAIL] {exc}")
            return 1

    timestamp = _now_utc()
    cases = build_probe_matrix(config.campaign_id, timestamp)

    if args.print_matrix:
        print("=== Probe matrix ===")
        for case in cases:
            print(f"- {case.probe}:{case.case_id} control={case.is_control}")
            print(f"  payload={_canonical_json(case.payload)}")

    client = ArchivistClient(config)  # type: ignore[arg-type]
    results: list[ProbeResult] = []
    try:
        for case in cases:
            result = await run_case(client, case, dry_run=args.dry_run)
            results.append(result)
            print(
                f"[{case.probe}:{case.case_id}] status={result.status_code} "
                f"accepted={result.accepted} created={result.created_item_id}"
            )
    finally:
        await client.aclose()

    type_summary = summarize_probe(results, "item_type_wire_format")
    mechanics_summary = summarize_probe(results, "mechanics_payload_shape")
    report_name = f"contract_probe_{timestamp}"
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "campaign_id": config.campaign_id,
        "dry_run": args.dry_run,
        "report_name": report_name,
        "probe_cases": [asdict(case) for case in cases],
        "probe_results": [asdict(result) for result in results],
        "summaries": {
            "item_type_wire_format": type_summary,
            "mechanics_payload_shape": mechanics_summary,
        },
        "suggested_validator_decision": validator_decision_text(type_summary, mechanics_summary),
        "mechanics_signature_examples": {
            "typed_object": _sha256(
                next(
                    c.payload["mechanics"]
                    for c in cases
                    if c.probe == "mechanics_payload_shape" and c.case_id == "typed_object"
                )
            ),
            "loose_object": _sha256(
                next(
                    c.payload["mechanics"]
                    for c in cases
                    if c.probe == "mechanics_payload_shape" and c.case_id == "loose_object"
                )
            ),
        },
    }
    markdown = to_markdown(
        timestamp=timestamp,
        report_name=report_name,
        results=results,
        type_summary=type_summary,
        mechanics_summary=mechanics_summary,
        campaign_id=config.campaign_id,
    )

    json_path, md_path = write_reports(Path(args.output_dir), report_name, report, markdown)
    print(f"\n[OK] JSON report: {json_path}")
    print(f"[OK] Markdown report: {md_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live contract probes for Archivist item paths.")
    parser.add_argument(
        "--output-dir",
        default="scripts/probe-results",
        help="Directory where JSON/Markdown reports are written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send API requests; emit report skeleton with probe matrix only.",
    )
    parser.add_argument(
        "--print-matrix",
        action="store_true",
        help="Print all probe payloads to stdout before execution.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
