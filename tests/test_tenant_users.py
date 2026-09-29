"""The Tenant users listing: licensed AND present in the report data.

A directory dump is not the answer to "who is this report about". dim_user
holds every member Graph returned, most of whom hold no Copilot licence and
appear in no Cowork report, so listing them all buries the rows anyone came
for.

The rows that must survive the filter are the awkward ones: someone holding a
licence who has done nothing. That is the row that answers "who are we paying
for and getting nothing from", so "present in the data" deliberately means
matched, not active.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import CoworkEvent, CoworkUsage, DirectoryUser

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _headers() -> dict[str, str]:
    # No admin group is configured, so this is a plain viewer; with no
    # org_view_group_id set either, the org view is open to them.
    return {"Authorization": f"Bearer {create_access_token('v@contoso.com', 'viewer')}"}


async def _user(uid: str, upn: str, name: str, *, licensed: bool | None):
    async with SessionLocal() as s:
        s.add(
            DirectoryUser(
                user_id=uid,
                upn=upn,
                display_name=name,
                account_enabled=True,
                user_type="Member",
                has_copilot_license=licensed,
            )
        )
        await s.commit()


async def _usage(upn: str, tasks: int):
    async with SessionLocal() as s:
        s.add(
            CoworkUsage(
                report_refresh_date=NOW.date(),
                report_period=28,
                user_principal_name=upn,
                total_tasks=tasks,
                active_days=1,
                last_activity_date=NOW - timedelta(days=1),
            )
        )
        await s.commit()


async def _event(event_id: str, *, upn: str | None = None, oid: str | None = None):
    async with SessionLocal() as s:
        s.add(
            CoworkEvent(
                event_id=event_id,
                created_at=NOW,
                user_id=oid,
                user_principal_name=upn,
                app_host="cowork",
            )
        )
        await s.commit()


async def _listing(client: httpx.AsyncClient) -> dict[str, dict]:
    r = await client.get("/metrics/users", headers=_headers())
    assert r.status_code == 200, r.text
    return {row["user_principal_name"]: row for row in r.json()}


# --------------------------------------------------------------------------- #
# The filter
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_licensed_user_with_usage_is_listed(client):
    await _user("u1", "ada@contoso.com", "Ada", licensed=True)
    await _usage("ada@contoso.com", 12)
    assert "ada@contoso.com" in await _listing(client)


@pytest.mark.asyncio
async def test_a_licensed_user_with_no_licence_is_excluded(client):
    await _user("u1", "ada@contoso.com", "Ada", licensed=False)
    await _usage("ada@contoso.com", 12)
    assert await _listing(client) == {}


@pytest.mark.asyncio
async def test_a_licensed_user_absent_from_the_report_data_is_excluded(client):
    """Licensed but never seen in any Cowork report — not what this page is for."""
    await _user("u1", "ada@contoso.com", "Ada", licensed=True)
    assert await _listing(client) == {}


@pytest.mark.asyncio
async def test_an_undetermined_licence_is_not_treated_as_licensed(client):
    """NULL means "never determined", which is not the same as licensed.

    The filter uses `is True` rather than truthiness for exactly this: a row
    that predates licence detection must not appear as though Graph had
    confirmed it.
    """
    await _user("u1", "ada@contoso.com", "Ada", licensed=None)
    await _usage("ada@contoso.com", 12)
    assert await _listing(client) == {}


@pytest.mark.asyncio
async def test_a_licensed_user_with_zero_activity_is_listed_not_hidden(client):
    """The whole point of the page: a paid licence producing nothing."""
    await _user("u1", "idle@contoso.com", "Idle", licensed=True)
    await _usage("idle@contoso.com", 0)
    row = (await _listing(client))["idle@contoso.com"]
    assert row["total_tasks"] == 0
    assert row["cowork_events"] == 0


@pytest.mark.asyncio
async def test_audit_events_alone_are_enough_to_be_present(client):
    """Cowork has two fact streams and only one needs to know about you."""
    await _user("u1", "ada@contoso.com", "Ada", licensed=True)
    await _event("e1", upn="ada@contoso.com")
    row = (await _listing(client))["ada@contoso.com"]
    assert row["cowork_events"] == 1
    assert row["total_tasks"] == 0


@pytest.mark.asyncio
async def test_events_matched_only_by_object_id_still_count(client):
    """The admin-centre exports carry a UPN; audit rows carry the object ID."""
    await _user("u1", "ada@contoso.com", "Ada", licensed=True)
    await _event("e1", oid="u1")
    row = (await _listing(client))["ada@contoso.com"]
    assert row["cowork_events"] == 1


@pytest.mark.asyncio
async def test_an_event_matching_by_both_keys_is_not_counted_twice(client):
    """A row carrying both the object ID and the UPN is one session, not two."""
    await _user("u1", "ada@contoso.com", "Ada", licensed=True)
    await _event("e1", upn="ada@contoso.com", oid="u1")
    await _event("e2", upn="ada@contoso.com", oid="u1")
    assert (await _listing(client))["ada@contoso.com"]["cowork_events"] == 2


@pytest.mark.asyncio
async def test_upn_casing_does_not_lose_a_match(client):
    """The directory and the admin-centre export disagree about case."""
    await _user("u1", "Ada@Contoso.com", "Ada", licensed=True)
    await _usage("ada@contoso.com", 7)
    assert (await _listing(client))["Ada@Contoso.com"]["total_tasks"] == 7


@pytest.mark.asyncio
async def test_tasks_are_summed_across_snapshots_not_multiplied_out(client):
    """Several report windows per person must not fan the join out."""
    await _user("u1", "ada@contoso.com", "Ada", licensed=True)
    await _usage("ada@contoso.com", 10)
    await _event("e1", upn="ada@contoso.com")
    await _event("e2", upn="ada@contoso.com")
    rows = await _listing(client)
    assert len(rows) == 1
    assert rows["ada@contoso.com"]["total_tasks"] == 10
    assert rows["ada@contoso.com"]["cowork_events"] == 2


@pytest.mark.asyncio
async def test_the_listing_is_organisation_gated(client):
    """It names colleagues and their usage, so it is not open to anyone signed in."""
    async with SessionLocal() as s:
        from shared.models import AppConfig

        s.add(AppConfig(id=1, azure_subscription_ids=[], org_view_group_id="g-1"))
        await s.commit()
    r = await client.get("/metrics/users", headers=_headers())
    assert r.status_code == 403
