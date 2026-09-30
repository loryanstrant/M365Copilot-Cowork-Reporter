"""The rebuilt personal page: aggregates, a per-day series, and comparisons.

Everything here reads fact_cowork_event.created_at, which is the only true
event timestamp the app holds. fact_cowork_usage is a snapshot per rolling
report window rather than a daily series, so it cannot answer "what did I do
on the 14th" at all — the old page trended by report period instead, which is
why the rebuild exists.

The comparison is the sensitive part. The personal page is reachable by every
signed-in user, including people with no organisation-wide access, so the
endpoint must return medians and a percentile and never another individual's
figures.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import CoworkEvent, DirectoryUser

NOW = datetime.now(timezone.utc)
ME_OID = "me-oid"
ME_UPN = "ada@contoso.com"


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _me() -> dict[str, str]:
    token = create_access_token("ada", "viewer", oid=ME_OID, upn=ME_UPN)
    return {"Authorization": f"Bearer {token}"}


async def _person(uid: str, upn: str, name: str, *, dept=None, manager=None):
    async with SessionLocal() as s:
        s.add(
            DirectoryUser(
                user_id=uid,
                upn=upn,
                display_name=name,
                department=dept,
                manager_name=manager,
                account_enabled=True,
                user_type="Member",
                has_copilot_license=True,
            )
        )
        await s.commit()


async def _event(eid, *, oid=ME_OID, days_ago=0, agent=None, tools=None, files=None):
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


# --------------------------------------------------------------------------- #
# Headline figures
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_activity_counts_sessions_tools_and_files(client):
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1", tools=["a", "b"], files=[{"id": "f1"}])
    await _event("e2", tools=["c"], files=[{"id": "f2"}, {"id": "f3"}])
    body = (await client.get("/metrics/me/activity", headers=_me())).json()
    assert body["sessions"] == 2
    assert body["tools"] == 3
    assert body["files"] == 3
    assert body["has_data"] is True


@pytest.mark.asyncio
async def test_activity_tolerates_events_with_no_tools_or_files(client):
    """The JSON columns are nullable, and NULL must count as nothing, not fail."""
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1", tools=None, files=None)
    body = (await client.get("/metrics/me/activity", headers=_me())).json()
    assert body["sessions"] == 1
    assert body["tools"] == 0
    assert body["files"] == 0


@pytest.mark.asyncio
async def test_activity_counts_distinct_active_days(client):
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1", days_ago=0)
    await _event("e2", days_ago=0)
    await _event("e3", days_ago=3)
    body = (await client.get("/metrics/me/activity", headers=_me())).json()
    assert body["sessions"] == 3
    assert body["active_days"] == 2


@pytest.mark.asyncio
async def test_activity_excludes_events_outside_the_window(client):
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("old", days_ago=90)
    await _event("new", days_ago=1)
    body = (await client.get("/metrics/me/activity?days=30", headers=_me())).json()
    assert body["sessions"] == 1


@pytest.mark.asyncio
async def test_activity_never_leaks_another_persons_events(client):
    await _person(ME_OID, ME_UPN, "Ada")
    await _person("other", "bob@contoso.com", "Bob")
    await _event("mine")
    await _event("theirs", oid="other")
    body = (await client.get("/metrics/me/activity", headers=_me())).json()
    assert body["sessions"] == 1


# --------------------------------------------------------------------------- #
# The per-day series
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_daily_returns_every_day_in_the_window(client):
    """Quiet days must be zeroes, not gaps.

    A bar chart built only from the days that happened rescales its axis and
    makes a fortnight of nothing look like continuous use.
    """
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1", days_ago=0)
    rows = (await client.get("/metrics/me/daily?days=30", headers=_me())).json()
    assert len(rows) == 30
    assert sum(r["sessions"] for r in rows) == 1
    assert rows[0]["sessions"] == 0  # 30 days ago, nothing


@pytest.mark.asyncio
async def test_daily_is_in_chronological_order(client):
    await _person(ME_OID, ME_UPN, "Ada")
    rows = (await client.get("/metrics/me/daily?days=7", headers=_me())).json()
    assert [r["day"] for r in rows] == sorted(r["day"] for r in rows)


@pytest.mark.asyncio
async def test_daily_buckets_events_onto_their_own_day(client):
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("a", days_ago=1)
    await _event("b", days_ago=1)
    await _event("c", days_ago=2)
    rows = (await client.get("/metrics/me/daily?days=7", headers=_me())).json()
    counts = [r["sessions"] for r in rows if r["sessions"]]
    assert sorted(counts) == [1, 2]


# --------------------------------------------------------------------------- #
# Top agents and tools
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_top_agents_ranks_by_session_count(client):
    await _person(ME_OID, ME_UPN, "Ada")
    for i in range(3):
        await _event(f"r{i}", agent="Researcher")
    await _event("a1", agent="Analyst")
    rows = (await client.get("/metrics/me/top-agents", headers=_me())).json()
    assert rows[0] == {"name": "Researcher", "value": 3}
    assert rows[1] == {"name": "Analyst", "value": 1}


@pytest.mark.asyncio
async def test_an_event_with_no_agent_is_labelled_not_dropped(client):
    """A session without a named agent is still a session."""
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1", agent=None)
    rows = (await client.get("/metrics/me/top-agents", headers=_me())).json()
    assert rows[0]["value"] == 1
    assert rows[0]["name"] == "cowork"  # falls back to app_host


@pytest.mark.asyncio
async def test_top_tools_counts_across_events(client):
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1", tools=["file_search", "web_search"])
    await _event("e2", tools=["file_search"])
    rows = (await client.get("/metrics/me/top-tools", headers=_me())).json()
    assert rows[0] == {"name": "file_search", "value": 2}
    assert rows[1] == {"name": "web_search", "value": 1}


@pytest.mark.asyncio
async def test_top_tools_handles_dict_shaped_entries(client):
    """Audit payloads are not perfectly consistent; a dict must not render as a repr."""
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1", tools=[{"name": "file_search"}, "web_search"])
    rows = (await client.get("/metrics/me/top-tools", headers=_me())).json()
    assert {r["name"] for r in rows} == {"file_search", "web_search"}


# --------------------------------------------------------------------------- #
# Standing: you vs your team vs the organisation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_standing_compares_against_team_and_organisation(client):
    """Five departmental peers — the smallest team that may be drawn at all.

    This fixture used to hold one peer, and the disclosure rule now withholds
    that. The peers are deliberately not all equal so the median is a real
    median, and the viewer is excluded from it: the bar answers "how do I
    compare with the rest of my team", not "how do I compare with a group I am
    a sixth of".
    """
    await _person(ME_OID, ME_UPN, "Ada", dept="Engineering")
    for i, count in enumerate([2, 3, 4, 5, 6]):
        await _person(f"t{i}", f"t{i}@contoso.com", f"Team mate {i}", dept="Engineering")
        for j in range(count):
            await _event(f"tm{i}-{j}", oid=f"t{i}")
    await _person("s1", "s1@contoso.com", "Someone", dept="Sales")

    for i in range(10):
        await _event(f"me{i}")
    await _event("s0", oid="s1")

    body = (await client.get("/metrics/me/standing", headers=_me())).json()
    assert body["team_state"] == "shown"
    assert body["team_label"] == "Engineering"
    sessions = next(s for s in body["stats"] if s["label"] == "Sessions")
    assert sessions["mine"] == 10
    assert sessions["team_people"] == 5
    assert sessions["org_people"] == 7
    # Peer sessions are [2, 3, 4, 5, 6] and I am not among them, so the team
    # median is 4. The organisation is all seven of us: [10, 6, 5, 4, 3, 2, 1].
    assert sessions["team_median"] == 4
    assert sessions["org_median"] == 4


@pytest.mark.asyncio
async def test_standing_falls_back_to_the_manager_when_no_department(client):
    """And the fallback group has to clear the same floor as a department."""
    await _person(ME_OID, ME_UPN, "Ada", manager="Grace Hopper")
    await _event("e1")
    for i in range(5):
        await _person(f"m{i}", f"m{i}@contoso.com", f"Report {i}", manager="Grace Hopper")
        await _event(f"m{i}a", oid=f"m{i}")

    body = (await client.get("/metrics/me/standing", headers=_me())).json()
    assert body["team_state"] == "shown"
    assert body["team_label"] == "Grace Hopper's team"
    assert body["team_peers"] == 5


@pytest.mark.asyncio
async def test_standing_withholds_a_manager_group_below_the_floor(client):
    """The old fixture: one manager peer, which is now withheld.

    Two people sharing a manager is the case the disclosure rule exists for —
    the group average and the viewer's own figure give the other person's
    number exactly.
    """
    await _person(ME_OID, ME_UPN, "Ada", manager="Grace Hopper")
    await _person("m0", "m0@contoso.com", "Report", manager="Grace Hopper")
    await _event("e1")
    await _event("m0a", oid="m0")

    body = (await client.get("/metrics/me/standing", headers=_me())).json()
    assert body["team_state"] == "too_small"
    assert body["team_label"] is None
    assert body["team_peers"] == 1


@pytest.mark.asyncio
async def test_standing_omits_the_team_when_it_cannot_be_identified(client):
    """No department and no manager means no team — not a team of zero.

    An empty team bar reads as "you are miles ahead of your colleagues" when it
    actually means "we do not know who your colleagues are".
    """
    await _person(ME_OID, ME_UPN, "Ada")
    await _event("e1")
    body = (await client.get("/metrics/me/standing", headers=_me())).json()
    assert body["team_label"] is None


@pytest.mark.asyncio
async def test_the_percentile_puts_the_busiest_person_at_the_top(client):
    await _person(ME_OID, ME_UPN, "Ada", dept="Engineering")
    await _person("t1", "t1@contoso.com", "Quiet", dept="Engineering")
    await _event("me1")
    await _event("me2")
    await _event("t1a", oid="t1")
    body = (await client.get("/metrics/me/standing", headers=_me())).json()
    assert body["org_percentile"] == 50  # did more than 1 of 2 people counted


@pytest.mark.asyncio
async def test_the_percentile_is_zero_when_everyone_is_level(client):
    """Ties count as "not more than", so level pegging is 0 rather than a
    flattering middle."""
    await _person(ME_OID, ME_UPN, "Ada", dept="Engineering")
    await _person("t1", "t1@contoso.com", "Same", dept="Engineering")
    await _event("me1")
    await _event("t1a", oid="t1")
    body = (await client.get("/metrics/me/standing", headers=_me())).json()
    assert body["org_percentile"] == 0


@pytest.mark.asyncio
async def test_standing_returns_no_individual_figures(client):
    """The safety property: medians and a percentile, never a person."""
    await _person(ME_OID, ME_UPN, "Ada", dept="Engineering")
    await _person("t1", "colleague@contoso.com", "Colleague", dept="Engineering")
    await _event("me1")
    await _event("t1a", oid="t1")
    raw = (await client.get("/metrics/me/standing", headers=_me())).text
    assert "colleague@contoso.com" not in raw
    assert "Colleague" not in raw
