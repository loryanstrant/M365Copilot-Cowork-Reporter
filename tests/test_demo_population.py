"""The demo tenant has to be big enough to show the features it ships with.

This is a regression test for a silent failure rather than a crash. The
personal page withholds its team comparison below MIN_TEAM_PEERS, and the
demo data used to seed six people across three departments — so the panel the
demo exists to demonstrate was withheld on every fresh instance, correctly and
invisibly. Nothing failed; the screen was simply missing.

Asserting it here rather than noticing it in a screenshot means a future
trim of the seed population fails the build instead of quietly emptying a
page nobody thinks to look at.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.routers.metrics import MIN_TEAM_PEERS
from scripts.seed_demo import _DEPARTMENTS, _NAMED_USERS, _population, seed
from shared.db import SessionLocal
from shared.models import AppUser
from shared.security import hash_password


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def test_every_department_clears_the_peer_floor():
    """Round-robin, so this holds for everyone rather than on average."""
    people = _population()
    sizes: dict[str, int] = {}
    for _upn, _name, dept, _mgr in people:
        sizes[dept] = sizes.get(dept, 0) + 1

    assert set(sizes) == set(_DEPARTMENTS)
    for dept, size in sizes.items():
        # size - 1 is the peer count for anyone in it: the floor is peers
        # besides the viewer, not members of the department.
        assert size - 1 >= MIN_TEAM_PEERS, f"{dept} has only {size - 1} peers"


def test_the_named_people_stay_and_stay_first():
    """They are load-bearing, so a reshuffle has to fail loudly.

    scripts/seed_demo.py indexes _USERS[0..2] for the chargeback mapping's
    business owners and binds the demo persona to user-0, both of which are
    positional. The Avanoso cast is also what docs/screenshots/README.md tells
    the next person to expect to see in the shots.
    """
    people = _population()
    assert [(u, n) for u, n, _d, _m in people[: len(_NAMED_USERS)]] == _NAMED_USERS
    assert len(people) >= 3, "the chargeback mapping indexes three business owners"


def test_the_population_is_deterministic_and_unique():
    """Two runs give the same tenant, and nobody shares a UPN."""
    first, second = _population(), _population()
    assert first == second
    upns = [u for u, *_ in first]
    assert len(set(upns)) == len(upns)


@pytest.mark.asyncio
async def test_the_seeded_persona_actually_sees_a_team(client):
    """End to end: seed the demo tenant, then read the panel as the persona.

    The local admin is bound to the seeded directory user by the seeder, which
    is what makes /me reachable without Entra — so signing in as the admin is
    signing in as the persona.
    """
    await seed(reset=True)
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    login = await client.post(
        "/auth/login", json={"username": "admin", "password": "pw"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    body = (await client.get("/metrics/me/standing?days=30", headers=headers)).json()

    assert body["team_state"] == "shown", (
        f"the demo persona's team was withheld ({body['team_peers']} peers) — "
        "the seeded population is too small to demonstrate the comparison"
    )
    assert body["team_peers"] >= MIN_TEAM_PEERS
    assert body["team_label"]
    assert all(st["team_median"] > 0 for st in body["stats"])


@pytest.mark.asyncio
async def test_the_seeded_run_history_shows_a_failure(client):
    """A run log where everything succeeded teaches nobody what a failure is."""
    await seed(reset=True)
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    login = await client.post(
        "/auth/login", json={"username": "admin", "password": "pw"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    rows = (await client.get("/admin/scan-history", headers=headers)).json()

    assert rows, "Scan history is empty on a freshly seeded instance"
    states = {r["state"] for r in rows}
    # All three indicators on screen at once: ● ◐ ○.
    assert {"succeeded", "running", "failed"} <= states
    failed = next(r for r in rows if r["state"] == "failed")
    assert failed["error"], "a failed run with no error is not worth listing"
    # The two kinds this app writes and no sibling does.
    kinds = {r["raw_kind"] for r in rows}
    assert {"csv-cowork-usage", "csv-credit-consumption"} <= kinds
    assert all(not r["kind"].startswith("csv-") for r in rows), "a csv kind went unlabelled"
