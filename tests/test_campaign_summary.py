"""Tests for campaign summary draft/commit (DESIGN.md step 12)."""

from __future__ import annotations

import json
import os
from urllib.parse import urlencode

import pytest

from archivist_mcp.errors import CommitPartialFailureError
from archivist_mcp.logging_ import reset_logging_configuration
from archivist_mcp.tools.campaign_summary import commit_campaign_summary, draft_campaign_summary
from tests.constants import CAMPAIGN_ID, JOURNAL_ID, SESSION_ID

WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
HISTORY_FOLDER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb0"
ARCHIVE_JOURNAL_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
OVERVIEW_FOLDER_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _wire_minimal_campaign_draft(httpx_mock: object) -> None:
    httpx_mock.reset()
    httpx_mock._options.assert_all_responses_were_requested = False
    base = os.environ["ARCHIVIST_BASE_URL"].rstrip("/")
    q = lambda **kw: urlencode(kw)
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/campaigns/{CAMPAIGN_ID}",
        json={
            "id": CAMPAIGN_ID,
            "title": "Camp",
            "description": "desc",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/sessions?{q(campaign_id=CAMPAIGN_ID, page=1, page_size=50)}",
        json={
            "data": [
                {
                    "id": SESSION_ID,
                    "title": "S1",
                    "session_date": "2026-01-02T00:00:00Z",
                }
            ],
            "page": 1,
            "pages": 1,
            "total": 1,
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/sessions/{SESSION_ID}",
        json={
            "id": SESSION_ID,
            "title": "S1",
            "summary": "sum",
            "session_date": "2026-01-02T00:00:00Z",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/quests?{q(campaign_id=CAMPAIGN_ID, page=1, page_size=50)}",
        json={"data": [], "page": 1, "pages": 1, "total": 0},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/campaigns/{CAMPAIGN_ID}/links?{q(page=1, page_size=50)}",
        json={"data": [], "page": 1, "pages": 1, "total": 0},
    )


@pytest.mark.asyncio
async def test_draft_campaign_summary_no_writes(httpx_mock: object) -> None:
    _wire_minimal_campaign_draft(httpx_mock)
    out = await draft_campaign_summary(guidance="g")
    assert "draft_markdown" in out
    for req in httpx_mock.get_requests():
        assert req.method not in WRITE_METHODS


@pytest.mark.asyncio
async def test_commit_campaign_description_equality_guard(httpx_mock: object) -> None:
    httpx_mock.reset()
    httpx_mock._options.assert_all_responses_were_requested = False
    base = os.environ["ARCHIVIST_BASE_URL"].rstrip("/")
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/campaigns/{CAMPAIGN_ID}",
        json={"id": CAMPAIGN_ID, "description": "x\n"},
    )
    r = await commit_campaign_summary("description", content="x")
    assert r.get("already_current") is True
    for req in httpx_mock.get_requests():
        assert req.method not in WRITE_METHODS


@pytest.mark.asyncio
async def test_commit_campaign_description_archive_then_patch(httpx_mock: object) -> None:
    httpx_mock.reset()
    httpx_mock._options.assert_all_responses_were_requested = False
    base = os.environ["ARCHIVIST_BASE_URL"].rstrip("/")
    qf = urlencode({"campaign_id": CAMPAIGN_ID, "page": 1, "page_size": 50})
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/campaigns/{CAMPAIGN_ID}",
        json={"id": CAMPAIGN_ID, "description": "old desc"},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/journal-folders?{qf}",
        json={
            "data": [{"id": HISTORY_FOLDER_ID, "name": "Summary History", "parent_id": None}],
            "page": 1,
            "pages": 1,
            "total": 1,
        },
    )
    httpx_mock.add_response(method="POST", url=f"{base}/v1/journals", json={"id": ARCHIVE_JOURNAL_ID}, status_code=201)
    httpx_mock.add_response(
        method="PATCH",
        url=f"{base}/v1/campaigns/{CAMPAIGN_ID}",
        json={"id": CAMPAIGN_ID, "description": "new desc"},
    )
    r = await commit_campaign_summary("description", content="new desc")
    assert r["archived_journal_id"] == ARCHIVE_JOURNAL_ID
    methods = [x.method for x in httpx_mock.get_requests()]
    assert methods.index("POST") < methods.index("PATCH")


@pytest.mark.asyncio
async def test_commit_campaign_description_patch_failure_after_archive(
    httpx_mock: object, capsys: pytest.CaptureFixture[str]
) -> None:
    httpx_mock.reset()
    httpx_mock._options.assert_all_responses_were_requested = False
    os.environ["ARCHIVIST_LOG_LEVEL"] = "INFO"
    reset_logging_configuration()
    base = os.environ["ARCHIVIST_BASE_URL"].rstrip("/")
    qf = urlencode({"campaign_id": CAMPAIGN_ID, "page": 1, "page_size": 50})
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/campaigns/{CAMPAIGN_ID}",
        json={"id": CAMPAIGN_ID, "description": "old desc"},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/journal-folders?{qf}",
        json={
            "data": [{"id": HISTORY_FOLDER_ID, "name": "Summary History", "parent_id": None}],
            "page": 1,
            "pages": 1,
            "total": 1,
        },
    )
    httpx_mock.add_response(method="POST", url=f"{base}/v1/journals", json={"id": ARCHIVE_JOURNAL_ID}, status_code=201)
    httpx_mock.add_response(
        method="PATCH",
        url=f"{base}/v1/campaigns/{CAMPAIGN_ID}",
        status_code=500,
        text="{}",
    )
    with pytest.raises(CommitPartialFailureError):
        await commit_campaign_summary("description", content="new desc")
    err_lines = [ln for ln in capsys.readouterr().err.splitlines() if ln.strip().startswith("{")]
    payloads = [json.loads(ln) for ln in err_lines]
    assert any(p.get("event") == "commit.partial_failure" for p in payloads)


@pytest.mark.asyncio
async def test_commit_campaign_overview_equality_and_write(httpx_mock: object) -> None:
    httpx_mock.reset()
    httpx_mock._options.assert_all_responses_were_requested = False
    base = os.environ["ARCHIVIST_BASE_URL"].rstrip("/")
    qf = urlencode({"campaign_id": CAMPAIGN_ID, "page": 1, "page_size": 50})
    ov_id = JOURNAL_ID
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/journal-folders?{qf}",
        json={
            "data": [{"id": OVERVIEW_FOLDER_ID, "name": "Campaign Overview", "parent_id": None}],
            "page": 1,
            "pages": 1,
            "total": 1,
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/journals?{qf}",
        json={
            "data": [
                {
                    "id": ov_id,
                    "title": "Campaign Overview",
                    "folder_id": OVERVIEW_FOLDER_ID,
                }
            ],
            "page": 1,
            "pages": 1,
            "total": 1,
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/journals/{ov_id}",
        json={
            "id": ov_id,
            "title": "Campaign Overview",
            "folder_id": OVERVIEW_FOLDER_ID,
            "content": "same",
        },
    )
    r = await commit_campaign_summary("overview", content="same")
    assert r.get("already_current") is True
