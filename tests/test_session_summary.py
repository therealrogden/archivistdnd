"""Tests for session summary draft/commit tools (DESIGN.md step 11)."""

from __future__ import annotations

import json
import os
from urllib.parse import urlencode

import pytest

from archivist_mcp.errors import CommitPartialFailureError
from archivist_mcp.logging_ import reset_logging_configuration
from archivist_mcp.tools.session_summary import commit_session_summary, draft_session_summary
from tests.constants import CAMPAIGN_ID, SESSION_ID

WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

HISTORY_FOLDER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb0"
ARCHIVE_JOURNAL_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


@pytest.mark.asyncio
async def test_draft_session_summary_no_writes(httpx_mock: object) -> None:
    out = await draft_session_summary(SESSION_ID, style="recap", include_cast_analysis=False)
    assert "draft_markdown" in out
    assert "prior_summary" in out
    assert SESSION_ID in out["session_id"]
    for req in httpx_mock.get_requests():
        assert req.method not in WRITE_METHODS


@pytest.mark.asyncio
async def test_commit_session_summary_equality_guard(httpx_mock: object) -> None:
    httpx_mock.reset()
    httpx_mock._options.assert_all_responses_were_requested = False
    base = os.environ["ARCHIVIST_BASE_URL"].rstrip("/")
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/sessions/{SESSION_ID}",
        json={
            "id": SESSION_ID,
            "campaign_id": CAMPAIGN_ID,
            "title": "S1",
            "summary": "hello\n",
            "session_date": "2026-01-01T00:00:00Z",
        },
    )
    r = await commit_session_summary(SESSION_ID, summary="hello")
    assert r.get("already_current") is True
    for req in httpx_mock.get_requests():
        assert req.method not in WRITE_METHODS


@pytest.mark.asyncio
async def test_commit_session_summary_archive_then_patch(httpx_mock: object) -> None:
    httpx_mock.reset()
    httpx_mock._options.assert_all_responses_were_requested = False
    base = os.environ["ARCHIVIST_BASE_URL"].rstrip("/")
    qf = urlencode({"campaign_id": CAMPAIGN_ID, "page": 1, "page_size": 50})
    httpx_mock.add_response(
        method="GET",
        url=f"{base}/v1/sessions/{SESSION_ID}",
        json={
            "id": SESSION_ID,
            "campaign_id": CAMPAIGN_ID,
            "title": "S1",
            "summary": "prior body",
            "session_date": "2026-01-01T00:00:00Z",
        },
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
    httpx_mock.add_response(
        method="POST",
        url=f"{base}/v1/journals",
        json={"id": ARCHIVE_JOURNAL_ID},
        status_code=201,
    )
    httpx_mock.add_response(
        method="PATCH",
        url=f"{base}/v1/sessions/{SESSION_ID}",
        json={
            "id": SESSION_ID,
            "summary": "new summary",
            "title": "S1",
        },
    )
    r = await commit_session_summary(SESSION_ID, summary="new summary")
    assert r.get("already_current") is not True
    assert r["prior_summary"] == "prior body"
    assert r["archived_journal_id"] == ARCHIVE_JOURNAL_ID
    methods = [x.method for x in httpx_mock.get_requests()]
    assert "POST" in methods and "PATCH" in methods
    post_i = next(i for i, m in enumerate(methods) if m == "POST")
    patch_i = next(i for i, m in enumerate(methods) if m == "PATCH")
    assert post_i < patch_i


@pytest.mark.asyncio
async def test_commit_session_summary_patch_failure_after_archive_logs(
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
        url=f"{base}/v1/sessions/{SESSION_ID}",
        json={
            "id": SESSION_ID,
            "campaign_id": CAMPAIGN_ID,
            "title": "S1",
            "summary": "prior body",
            "session_date": "2026-01-01T00:00:00Z",
        },
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
    httpx_mock.add_response(
        method="POST",
        url=f"{base}/v1/journals",
        json={"id": ARCHIVE_JOURNAL_ID},
        status_code=201,
    )
    httpx_mock.add_response(
        method="PATCH",
        url=f"{base}/v1/sessions/{SESSION_ID}",
        status_code=500,
        text='{"detail":"no"}',
    )
    with pytest.raises(CommitPartialFailureError) as ei:
        await commit_session_summary(SESSION_ID, summary="new summary")
    assert ei.value.orphan["folder_id"] == HISTORY_FOLDER_ID
    assert ei.value.orphan["journal_id"] == ARCHIVE_JOURNAL_ID
    assert "title" in ei.value.orphan
    err_lines = [ln for ln in capsys.readouterr().err.splitlines() if ln.strip().startswith("{")]
    payloads = [json.loads(ln) for ln in err_lines]
    partial = [p for p in payloads if p.get("event") == "commit.partial_failure"]
    assert partial and partial[0]["tool"] == "commit_session_summary"
