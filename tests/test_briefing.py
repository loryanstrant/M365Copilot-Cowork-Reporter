"""The executive briefing.

Deterministic by design: every figure is SQL and the page assembles its
sentences from those figures against fixed thresholds. No model is involved
anywhere, because this is the screen most likely to be shown to a customer and
one invented number there costs more than the feature is worth.

The tests that matter are the arithmetic ones — period boundaries, and the
percentage change when the previous period was zero.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import CoworkEvent, DailyCost, DirectoryUser

NOW = datetime.now(timezone.utc)
TODAY = date.today()


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('v@x.com', 'viewer')}"}


async def _event(eid, *, days_ago, oid="u1", agent=None, tools=None, files=None):
    async with SessionLocal() as s:
        s.add(
            CoworkEvent(
                event_id=eid,
                created_at=NOW - timedelta(days=days_ago),
                user_id=oid,
                app_host="cowork",
                agent_name=agent,
                tools=tools,
                accessed_resources=files,
            )
        )
        await s.commit()


async def _cost(rg, amount, *, days_ago):
    async with SessionLocal() as s:
        s.add(
            DailyCost(
                cost_date=TODAY - timedelta(days=days_ago),
                subscription_id="sub-1",
                resource_group=rg,
                cost=amount,
                currency="AUD",
            )
        )
        await s.commit()


async def _licensed(uid, upn, *, licensed=True):
    async with SessionLocal() as s:
        s.add(
            DirectoryUser(
                user_id=uid,
                upn=upn,
                display_name=uid,
                account_enabled=True,
                has_copilot_license=licensed,
            )
        )
        await s.commit()


async def _get(client) -> dict:
    r = await client.get("/metrics/briefing?days=30", headers=_headers())
    assert r.status_code == 200, r.text
    return r.json()


def _delta(body, label):
    return next(d for d in body["deltas"] if d["label"] == label)


# --------------------------------------------------------------------------- #
# Period arithmetic
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_two_periods_do_not_overlap(client):
    """The boundary is the bug worth pinning: one event, counted once."""
    await _event("cur", days_ago=5)
    await _event("prev", days_ago=40)
    body = await _get(client)
    sessions = _delta(body, "Sessions")
    assert sessions["current"] == 1
    assert sessions["previous"] == 1


@pytest.mark.asyncio
async def test_events_older_than_both_periods_are_excluded(client):
    await _event("ancient", days_ago=200)
    body = await _get(client)
    sessions = _delta(body, "Sessions")
    assert sessions["current"] == 0
    assert sessions["previous"] == 0


@pytest.mark.asyncio
async def test_change_is_a_percentage_of_the_previous_period(client):
    for i in range(4):
        await _event(f"c{i}", days_ago=3)
    for i in range(2):
        await _event(f"p{i}", days_ago=40)
    assert _delta(await _get(client), "Sessions")["change_pct"] == 100.0


@pytest.mark.asyncio
async def test_a_fall_is_reported_as_a_negative_change(client):
    await _event("c0", days_ago=3)
    for i in range(4):
        await _event(f"p{i}", days_ago=40)
    assert _delta(await _get(client), "Sessions")["change_pct"] == -75.0


@pytest.mark.asyncio
async def test_growth_from_nothing_has_no_percentage(client):
    """"Up from zero" is not +100% and is not infinity.

    Null lets the page say "new this period" instead of printing a number that
    means nothing — which on an executive screen is the whole difference
    between a briefing and a liability.
    """
    await _event("c0", days_ago=3)
    assert _delta(await _get(client), "Sessions")["change_pct"] is None


# --------------------------------------------------------------------------- #
# What it counts
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_tools_and_files_are_summed_from_the_json_columns(client):
    await _event("e1", days_ago=1, tools=["a", "b"], files=[{"id": "f"}])
    await _event("e2", days_ago=2, tools=["c"], files=None)
    body = await _get(client)
    assert _delta(body, "Tools used")["current"] == 3
    assert _delta(body, "Files touched")["current"] == 1


@pytest.mark.asyncio
async def test_cost_is_summed_per_period_with_its_currency(client):
    await _cost("rg-a", 100, days_ago=2)
    await _cost("rg-b", 50, days_ago=3)
    await _cost("rg-a", 60, days_ago=40)
    body = await _get(client)
    cost = _delta(body, "Azure cost")
    assert cost["current"] == 150
    assert cost["previous"] == 60
    assert body["currency"] == "AUD"


@pytest.mark.asyncio
async def test_licence_adoption_counts_only_licensed_people(client):
    await _licensed("u1", "a@x.com")
    await _licensed("u2", "b@x.com")
    await _licensed("u3", "c@x.com", licensed=False)
    await _event("e1", days_ago=1, oid="u1")
    await _event("e2", days_ago=1, oid="u3")  # unlicensed, must not count
    body = await _get(client)
    assert body["licensed_users"] == 2
    assert body["active_licensed_users"] == 1
    assert body["idle_licensed_users"] == 1


@pytest.mark.asyncio
async def test_a_licensed_person_active_twice_counts_once(client):
    await _licensed("u1", "a@x.com")
    await _event("e1", days_ago=1, oid="u1")
    await _event("e2", days_ago=2, oid="u1")
    assert (await _get(client))["active_licensed_users"] == 1


@pytest.mark.asyncio
async def test_top_agents_carry_their_previous_period_figure(client):
    for i in range(3):
        await _event(f"c{i}", days_ago=2, agent="Researcher")
    await _event("p0", days_ago=40, agent="Researcher")
    top = (await _get(client))["top_agents"][0]
    assert top["name"] == "Researcher"
    assert top["value"] == 3
    assert top["previous"] == 1


@pytest.mark.asyncio
async def test_top_resource_groups_rank_by_cost(client):
    await _cost("rg-big", 900, days_ago=2)
    await _cost("rg-small", 10, days_ago=2)
    rgs = (await _get(client))["top_resource_groups"]
    assert [r["name"] for r in rgs] == ["rg-big", "rg-small"]


@pytest.mark.asyncio
async def test_an_empty_deployment_reports_no_data_rather_than_zeros(client):
    body = await _get(client)
    assert body["has_data"] is False


@pytest.mark.asyncio
async def test_the_briefing_is_organisation_gated(client):
    """It is a tenant-wide summary, so it is not open to every signed-in user."""
    async with SessionLocal() as s:
        from shared.models import AppConfig

        s.add(AppConfig(id=1, azure_subscription_ids=[], org_view_group_id="g-1"))
        await s.commit()
    r = await client.get("/metrics/briefing", headers=_headers())
    assert r.status_code == 403
