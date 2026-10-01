"""The manual tenant-user import.

This exists because the licence flag on dim_user is written by exactly one
collector, and that collector only ran on a schedule. A tenant whose schedule
had not come round since that code shipped showed an empty Tenant users page
and no licence adoption, and there was no way to fix it from inside the
product — it took a database query to even see what was wrong.

It is deliberately *not* a full collection: cost and the Purview audit feed are
slow and rate-limited, and the point is a cheap refresh of who exists.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from api.routers import admin as admin_router


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


@pytest.mark.asyncio
async def test_refusing_to_run_twice_is_an_answer_not_an_error(client):
    """A second press while one is running is normal, and says so."""
    await admin_router._user_sync_lock.acquire()
    try:
        r = await client.post("/admin/users/refresh", headers=_admin())
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "already_running"
        assert "progress" in body["detail"]
    finally:
        admin_router._user_sync_lock.release()


@pytest.mark.asyncio
async def test_it_does_not_share_a_lock_with_the_full_collection(client):
    """A long collection must not block a short directory read, or vice versa.

    They touch different things and take wildly different times; one lock would
    mean a backfill running overnight blocks the button that exists precisely
    for when you cannot wait.
    """
    assert admin_router._user_sync_lock is not admin_router._ingest_lock


def test_the_user_sync_is_a_separate_entry_point():
    """It must not be run_ingest under another name — that would drag cost and
    the audit feed along, which is the whole thing being avoided."""
    from worker.ingest import run_ingest, run_user_sync

    assert run_user_sync is not run_ingest
    src = run_user_sync.__doc__ or ""
    assert "directory" in src.lower()
