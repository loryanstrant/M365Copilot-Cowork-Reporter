"""Scan history: two untidy vocabularies rendered without losing a run.

The page's whole value is that it lists every collection that happened. So the
tests worth having are the ones about *not dropping rows*: a job kind this
build has no label for, a status written by a different module under a
different word, and a nested stats blob whose numbers would otherwise be
filtered out as "not a number".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.metrics import JOB_KIND_LABELS, JOB_STATUS_STATE, scan_history
from shared.db import SessionLocal
from shared.models import AppUser, JobRun
from shared.security import hash_password

NOW = datetime(2026, 9, 30, 2, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _add(**kwargs) -> None:
    async with SessionLocal() as s:
        s.add(JobRun(**kwargs))
        await s.commit()


def test_every_kind_this_app_writes_has_a_label():
    """The five job_name values in this codebase, plus the siblings' three.

    A kind written by the code and missing from the table renders as a raw
    string like "csv-cowork-usage" in front of an administrator.
    """
    for kind in (
        "scheduled",
        "manual",
        "backfill",
        "csv-cowork-usage",
        "csv-credit-consumption",
        "daily",
        "users",
    ):
        assert kind in JOB_KIND_LABELS, kind


def test_success_and_completed_are_one_state():
    """They differ only by which module wrote the row, not by meaning."""
    assert JOB_STATUS_STATE["success"] == JOB_STATUS_STATE["completed"] == "succeeded"
    assert JOB_STATUS_STATE["running"] == JOB_STATUS_STATE["preparing"] == "running"


@pytest.mark.asyncio
async def test_unrecognised_kind_renders_raw_rather_than_vanishing(session):
    """A run that happened and is not listed is worse than one labelled oddly."""
    await _add(job_name="some-future-collector", status="success", started_at=NOW)

    rows = await scan_history(session)

    assert len(rows) == 1
    assert rows[0]["kind"] == "some-future-collector"
    assert rows[0]["raw_kind"] == "some-future-collector"


@pytest.mark.asyncio
async def test_unrecognised_status_survives_too(session):
    await _add(job_name="manual", status="weird", started_at=NOW)

    rows = await scan_history(session)

    assert rows[0]["state"] == "weird"
    assert rows[0]["raw_status"] == "weird"


@pytest.mark.asyncio
async def test_nested_ingest_stats_keep_their_group(session):
    """A scheduled ingest nests each collector's counts under its own name.

    Flattened to the leaf key alone, "cost.rows" and an upload's "rows" would
    collide and the page would call both of them the same thing.
    """
    await _add(
        job_name="scheduled",
        status="success",
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=95),
        stats={
            "users": {"users": 90, "copilot_licensed": 64},
            "cost": {"subscriptions": 1, "rows": 450, "window_days": 30},
            "audit": {"scanned": 800, "cowork_events": 312},
        },
    )

    rows = await scan_history(session)

    assert rows[0]["stats"]["cost.rows"] == 450
    assert rows[0]["stats"]["audit.cowork_events"] == 312
    assert rows[0]["stats"]["users.users"] == 90
    assert rows[0]["duration_seconds"] == 95


@pytest.mark.asyncio
async def test_a_failure_surfaces_its_error_and_keeps_its_counts(session):
    """The error is lifted out of stats; what the run managed is still shown."""
    await _add(
        job_name="scheduled",
        status="failed",
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=12),
        stats={"users": {"users": 90}, "error": "Graph returned 429 after 5 retries"},
    )

    rows = await scan_history(session)

    assert rows[0]["state"] == "failed"
    assert rows[0]["error"] == "Graph returned 429 after 5 retries"
    assert "error" not in rows[0]["stats"]
    assert rows[0]["stats"]["users.users"] == 90


@pytest.mark.asyncio
async def test_a_run_still_going_has_no_duration(session):
    await _add(job_name="backfill", status="running", started_at=NOW)

    rows = await scan_history(session)

    assert rows[0]["state"] == "running"
    assert rows[0]["duration_seconds"] is None
    assert rows[0]["finished_at"] is None


@pytest.mark.asyncio
async def test_newest_first(session):
    await _add(job_name="manual", status="success", started_at=NOW - timedelta(days=2))
    await _add(job_name="manual", status="success", started_at=NOW)

    rows = await scan_history(session)

    assert rows[0]["started_at"] > rows[1]["started_at"]


@pytest.mark.asyncio
async def test_endpoint_is_admin_only(client):
    """A run log names collectors and errors, which is operational detail."""
    anonymous = await client.get("/admin/scan-history")
    assert anonymous.status_code in (401, 403)

    headers = await _admin_headers(client)
    await _add(
        job_name="csv-cowork-usage",
        status="success",
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=3),
        stats={"rows": 120, "imported": 118, "skipped": 2},
    )

    r = await client.get("/admin/scan-history", headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body[0]["kind"] == "Usage CSV upload"
    assert body[0]["state"] == "succeeded"
    assert body[0]["stats"]["rows"] == 120
