"""The team comparison, and the disclosure rule that governs when it appears.

The security-relevant claim is a counting one: below five peers the team figure
plus the viewer's own figure narrows an individual's number, and at exactly two
people it gives it exactly. So the tests here are mostly about the team series
*not* being drawn, and about the withheld figure never reaching the browser —
a number the page receives and then chooses not to render has still been
disclosed to anyone who opens the network tab.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from api.routers.metrics import MIN_TEAM_PEERS
from shared.db import SessionLocal
from shared.models import CoworkEvent, DirectoryUser

ME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MY_UPN = "me@contoso.com"


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _headers() -> dict[str, str]:
    token = create_access_token(MY_UPN, "viewer", oid=ME, upn=MY_UPN)
    return {"Authorization": f"Bearer {token}"}


async def _person(
    session,
    *,
    user_id: str,
    upn: str,
    department: str | None,
    manager: str | None = None,
    sessions: int = 3,
) -> None:
    session.add(
        DirectoryUser(
            user_id=user_id,
            upn=upn,
            display_name=upn.split("@")[0],
            department=department,
            manager_name=manager,
            has_copilot_license=True,
        )
    )
    now = datetime.now(timezone.utc)
    for i in range(sessions):
        session.add(
            CoworkEvent(
                event_id=f"{user_id}-{i}",
                created_at=now - timedelta(days=1, minutes=i),
                user_id=user_id,
                user_principal_name=upn,
                agent_name="Researcher",
                tools=["file_search"],
                accessed_resources=["Board pack.pptx"],
            )
        )


async def _seed(*, peers_in_my_department: int, my_manager: str | None = None,
                manager_peers: int = 0, my_department: str | None = "Engineering") -> None:
    """Me, some departmental peers, a manager group, and an unrelated crowd.

    The unrelated crowd exists so the organisation series always has a real
    population behind it — otherwise "the organisation" would be my own team
    and the two bars would agree by construction.
    """
    async with SessionLocal() as s:
        await _person(
            s, user_id=ME, upn=MY_UPN, department=my_department,
            manager=my_manager, sessions=9,
        )
        for i in range(peers_in_my_department):
            await _person(
                s, user_id=f"dept-{i}", upn=f"dept{i}@contoso.com",
                department=my_department, manager=my_manager, sessions=2,
            )
        for i in range(manager_peers):
            await _person(
                s, user_id=f"mgr-{i}", upn=f"mgr{i}@contoso.com",
                department=f"Other {i}", manager=my_manager, sessions=4,
            )
        for i in range(12):
            await _person(
                s, user_id=f"org-{i}", upn=f"org{i}@contoso.com",
                department="Somewhere else", sessions=1,
            )
        await s.commit()


async def _standing(client: httpx.AsyncClient) -> dict:
    r = await client.get("/metrics/me/standing?days=30", headers=_headers())
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_a_team_at_the_floor_is_shown(client):
    await _seed(peers_in_my_department=MIN_TEAM_PEERS)

    body = await _standing(client)

    assert body["team_state"] == "shown"
    assert body["team_label"] == "Engineering"
    assert body["team_peers"] == MIN_TEAM_PEERS
    assert all(s["team_median"] > 0 for s in body["stats"])


@pytest.mark.asyncio
async def test_one_peer_below_the_floor_is_withheld(client):
    """Four peers is not "nearly five" — it is a team that identifies people."""
    await _seed(peers_in_my_department=MIN_TEAM_PEERS - 1)

    body = await _standing(client)

    assert body["team_state"] == "too_small"
    assert body["team_label"] is None
    assert body["team_peers"] == MIN_TEAM_PEERS - 1


@pytest.mark.asyncio
async def test_a_team_of_two_never_sends_the_figure(client):
    """The arithmetic this rule exists to prevent.

    With one peer, a team average plus the viewer's own number gives the other
    person's exact figure. Withholding it in the page would not be enough — the
    response itself must not carry it.
    """
    await _seed(peers_in_my_department=1)

    body = await _standing(client)

    assert body["team_state"] == "too_small"
    assert all(s["team_median"] == 0 for s in body["stats"])
    assert all(s["team_people"] == 0 for s in body["stats"])


@pytest.mark.asyncio
async def test_a_department_of_one_is_too_small_not_unknown(client):
    """The department is on file. It is simply below the floor.

    Reporting this as "we don't know your team" would send an administrator
    hunting a data-quality problem that is not there, which is the whole reason
    the two states are distinguished rather than collapsed into "no team".
    """
    await _seed(peers_in_my_department=0)

    body = await _standing(client)

    assert body["team_state"] == "too_small"
    assert body["team_label"] is None
    assert body["team_peers"] == 0


@pytest.mark.asyncio
async def test_a_sole_report_to_a_manager_is_also_too_small(client):
    """Same reasoning down the manager path, which had the same bug."""
    await _seed(
        peers_in_my_department=0, my_department=None, my_manager="Ping Lim",
    )

    body = await _standing(client)

    assert body["team_state"] == "too_small"
    assert body["team_peers"] == 0


@pytest.mark.asyncio
async def test_stray_whitespace_does_not_lose_a_peer(client):
    """Entra's department field is hand-maintained often enough to matter.

    A trailing space on one row would silently drop a real colleague, and
    dropping one is enough to push a team of exactly five under the floor.
    """
    await _seed(peers_in_my_department=MIN_TEAM_PEERS)
    async with SessionLocal() as s:
        row = await s.get(DirectoryUser, "dept-0")
        row.department = "Engineering "
        await s.commit()

    body = await _standing(client)

    assert body["team_state"] == "shown"
    assert body["team_peers"] == MIN_TEAM_PEERS


@pytest.mark.asyncio
async def test_no_department_and_no_manager_reads_as_unknown(client):
    """A different fact from "too small", and the page says which."""
    await _seed(peers_in_my_department=0, my_department=None)

    body = await _standing(client)

    assert body["team_state"] == "unknown"
    assert body["team_peers"] == 0


@pytest.mark.asyncio
async def test_a_small_department_falls_back_to_the_manager_group(client):
    """The fallback is only worth taking when it is bigger."""
    await _seed(
        peers_in_my_department=2,
        my_manager="Ping Lim",
        manager_peers=MIN_TEAM_PEERS,
    )

    body = await _standing(client)

    assert body["team_state"] == "shown"
    assert body["team_label"] == "Ping Lim's team"
    # The two departmental peers share the manager, so they are in the group
    # too: five unrelated reports plus them.
    assert body["team_peers"] == MIN_TEAM_PEERS + 2


@pytest.mark.asyncio
async def test_falling_back_to_a_group_that_is_also_too_small_still_withholds(client):
    """Swapping a department of three for a manager group of four fixes nothing."""
    await _seed(
        peers_in_my_department=2,
        my_manager="Ping Lim",
        manager_peers=1,
    )

    body = await _standing(client)

    assert body["team_state"] == "too_small"
    assert body["team_label"] is None


@pytest.mark.asyncio
async def test_the_panel_is_told_the_period_and_the_population(client):
    await _seed(peers_in_my_department=MIN_TEAM_PEERS)

    body = await _standing(client)

    assert body["period_days"] == 30
    assert body["period_from"] and body["period_to"]
    assert body["period_from"] < body["period_to"]
    # 1 me + 5 peers + 12 others, all of whom have activity in the window.
    assert body["org_people"] == 18
    assert body["min_team_peers"] == MIN_TEAM_PEERS


@pytest.mark.asyncio
async def test_the_percentile_is_measured_against_the_organisation(client):
    """I did 9 sessions; everyone else did 1 or 2, so I am the busiest.

    That is 94, not 100: the population is the organisation including me, and
    being the busiest of 18 people puts me above 17 of them — the top 6%, not
    the top 0%. A percentile that hit 100 would be counting a population the
    viewer had been removed from, which is not what the panel claims.
    """
    await _seed(peers_in_my_department=MIN_TEAM_PEERS)

    body = await _standing(client)

    assert body["org_people"] == 18
    assert body["org_percentile"] == 94
    assert body["org_people"] > body["team_peers"]


@pytest.mark.asyncio
async def test_the_team_median_excludes_the_viewer(client):
    """Otherwise the bar is dragged toward the figure it is compared against.

    I did 9 sessions and each peer did 2. A median over the team including me
    would be 2 as well here, so the test checks the peer count rather than
    relying on the numbers to differ.
    """
    await _seed(peers_in_my_department=MIN_TEAM_PEERS)

    body = await _standing(client)

    sessions = next(s for s in body["stats"] if s["label"] == "Sessions")
    assert sessions["team_people"] == MIN_TEAM_PEERS
    assert sessions["mine"] == 9
    assert sessions["team_median"] == 2
