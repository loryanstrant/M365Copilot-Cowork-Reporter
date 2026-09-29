"""The demo persona: personal pages that work without Entra, and go away after.

The personal view scopes to the signed-in person's Entra identity. The local
password admin has none, so before this the README's own invitation — press
Load demo data and look around — led to personal pages that could not be
reached at all. The feature looked broken rather than gated.

The risk in fixing it is the opposite failure: a persona surviving a cutover to
real data, so the admin sees a fictional person's activity presented as their
own. That is worse than stale rows, because it is wrong about *whose* data it
is. These tests pin both ends.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from shared.db import SessionLocal
from shared.demo import (
    bind_demo_persona,
    get_demo_persona_user_id,
    retire_demo_persona,
)
from shared.models import AppUser, DirectoryUser
from shared.security import hash_password


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


async def _bind(upn="ada@contoso.com", name="Ada Lovelace", uid="user-0"):
    """Seed a directory user and bind the local admin to it."""
    async with SessionLocal() as s:
        s.add(
            DirectoryUser(
                user_id=uid,
                upn=upn,
                display_name=name,
                account_enabled=True,
                user_type="Member",
            )
        )
        await bind_demo_persona(s, user_id=uid)
        await s.commit()


# --------------------------------------------------------------------------- #
# Without a persona
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_local_admin_has_no_personal_view_by_default(client):
    """Production behaviour, unchanged: no directory identity, no personal view."""
    body = (await client.get("/auth/me", headers=await _admin_headers(client))).json()
    assert body["has_personal_view"] is False


@pytest.mark.asyncio
async def test_the_personal_endpoints_404_without_a_persona(client):
    headers = await _admin_headers(client)
    r = await client.get("/metrics/me/summary", headers=headers)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# With one bound
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_bound_persona_unlocks_the_personal_view(client):
    headers = await _admin_headers(client)
    await _bind()
    body = (await client.get("/auth/me", headers=headers)).json()
    assert body["has_personal_view"] is True


@pytest.mark.asyncio
async def test_the_sidebar_shows_the_persona_not_the_account(client):
    """The account is called "admin", which says nothing about who is on screen."""
    headers = await _admin_headers(client)
    await _bind()
    body = (await client.get("/auth/me", headers=headers)).json()
    assert body["display_name"] == "Ada Lovelace"
    assert body["upn"] == "ada@contoso.com"
    # The account name is still reported; it is simply not the headline.
    assert body["username"] == "admin"


@pytest.mark.asyncio
async def test_the_personal_endpoints_resolve_to_the_persona(client):
    headers = await _admin_headers(client)
    await _bind()
    r = await client.get("/metrics/me/summary", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["user_principal_name"] == "ada@contoso.com"


@pytest.mark.asyncio
async def test_a_persona_never_overrides_a_real_entra_identity(client):
    """Someone signed in with a work account must see themselves, not the demo."""
    from api.auth import create_access_token

    await _bind()
    token = create_access_token(
        "real@contoso.com",
        "viewer",
        oid="real-oid",
        upn="real@contoso.com",
        display_name="Real Person",
    )
    body = (
        await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    ).json()
    assert body["upn"] == "real@contoso.com"
    assert body["display_name"] == "Real Person"


# --------------------------------------------------------------------------- #
# Retiring it
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_clearing_demo_data_retires_the_persona(client):
    from scripts.seed_demo import clear

    headers = await _admin_headers(client)
    await _bind()
    await clear()
    body = (await client.get("/auth/me", headers=headers)).json()
    assert body["has_personal_view"] is False


@pytest.mark.asyncio
async def test_retire_is_idempotent():
    """Clear demo data can be pressed twice, and a real ingest runs repeatedly."""
    async with SessionLocal() as s:
        await retire_demo_persona(s)
        await retire_demo_persona(s)
        await s.commit()
        assert await get_demo_persona_user_id(s) is None


@pytest.mark.asyncio
async def test_a_persona_pointing_at_a_deleted_user_is_not_a_personal_view(client):
    """Bound to a row that is no longer there — do not show a view scoped to nobody."""
    headers = await _admin_headers(client)
    async with SessionLocal() as s:
        await bind_demo_persona(s, user_id="ghost")
        await s.commit()
    body = (await client.get("/auth/me", headers=headers)).json()
    assert body["has_personal_view"] is False


@pytest.mark.asyncio
async def test_a_non_admin_password_account_does_not_inherit_the_persona(client):
    """The binding exists for whoever loaded the demo data, not for everyone."""
    from api.auth import create_access_token

    await _bind()
    token = create_access_token("viewer-acct", "viewer")
    body = (
        await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    ).json()
    assert body["has_personal_view"] is False
