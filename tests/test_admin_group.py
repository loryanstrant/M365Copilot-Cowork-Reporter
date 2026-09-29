"""The Entra admin group, and the display name carried from the ID token.

The security-relevant claims here are:

- an unset admin group grants admin to *nobody*, so upgrading an existing
  deployment cannot hand administration to everyone who can sign in;
- membership is re-read per request, so it is the group that decides, not a
  role baked into a long-lived token;
- the local password admin keeps working regardless, because it is the account
  used to configure the group in the first place.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import AppConfig, AppUser
from shared.security import hash_password

OID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ADMIN_GROUP = "dddddddd-dddd-dddd-dddd-dddddddddddd"
OTHER_GROUP = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _set_admin_group(group_id: str | None) -> None:
    async with SessionLocal() as s:
        cfg = await s.get(AppConfig, 1)
        if cfg is None:
            cfg = AppConfig(id=1, azure_subscription_ids=[])
            s.add(cfg)
        cfg.admin_group_id = group_id
        await s.commit()


def _sso_headers(*, display_name: str | None = None) -> dict[str, str]:
    """An Entra sign-in. Always minted as a viewer, exactly as the callback does."""
    token = create_access_token(
        "ada@contoso.com",
        "viewer",
        oid=OID,
        upn="ada@contoso.com",
        display_name=display_name,
    )
    return {"Authorization": f"Bearer {token}"}


async def _local_admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _member_of(*group_ids: str):
    """Stub the Graph group check. Patched on api.oidc, which api.auth imports
    lazily inside the call, so the patch is seen at call time."""

    async def _check(principal, group_id, session):
        return group_id in group_ids

    return _check


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unset_admin_group_grants_admin_to_nobody(client):
    """Fails closed — the opposite of the organisation-view group."""
    await _set_admin_group(None)
    r = await client.get("/admin/config", headers=_sso_headers())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_group_member_gets_admin(client, monkeypatch):
    await _set_admin_group(ADMIN_GROUP)

    import api.oidc as oidc

    monkeypatch.setattr(oidc, "is_group_member", _member_of(ADMIN_GROUP))
    r = await client.get("/admin/config", headers=_sso_headers())
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_non_member_is_refused(client, monkeypatch):
    await _set_admin_group(ADMIN_GROUP)

    import api.oidc as oidc

    monkeypatch.setattr(oidc, "is_group_member", _member_of(OTHER_GROUP))
    r = await client.get("/admin/config", headers=_sso_headers())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_local_admin_administers_without_any_group(client):
    """The account used to set the group must not depend on the group."""
    await _set_admin_group(None)
    headers = await _local_admin_headers(client)
    r = await client.get("/admin/config", headers=headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_admin_via_group_can_write_config(client, monkeypatch):
    """Read access is not the whole grant — the write path uses the same gate."""
    await _set_admin_group(ADMIN_GROUP)

    import api.oidc as oidc

    monkeypatch.setattr(oidc, "is_group_member", _member_of(ADMIN_GROUP))
    r = await client.put(
        "/admin/config", headers=_sso_headers(), json={"tenant_id": "tenant-1"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["tenant_id"] == "tenant-1"


@pytest.mark.asyncio
async def test_the_admin_group_survives_a_round_trip_through_settings(client):
    """Setting it is the whole point, and it is not a secret — it reads back."""
    headers = await _local_admin_headers(client)
    r = await client.put(
        "/admin/config", headers=headers, json={"admin_group_id": ADMIN_GROUP}
    )
    assert r.status_code == 200, r.text
    assert r.json()["admin_group_id"] == ADMIN_GROUP
    # Blanking it closes the gate again rather than storing an empty string.
    r = await client.put("/admin/config", headers=headers, json={"admin_group_id": "  "})
    assert r.json()["admin_group_id"] is None


@pytest.mark.asyncio
async def test_group_admin_reaches_an_org_gated_endpoint(client, monkeypatch):
    """can_view_org defers to is_admin, so admin-by-group implies the org view
    without needing to also be in the organisation-view group."""
    async with SessionLocal() as s:
        cfg = AppConfig(id=1, azure_subscription_ids=[])
        cfg.admin_group_id = ADMIN_GROUP
        cfg.org_view_group_id = OTHER_GROUP
        s.add(cfg)
        await s.commit()

    import api.oidc as oidc

    monkeypatch.setattr(oidc, "is_group_member", _member_of(ADMIN_GROUP))
    r = await client.get("/metrics/kpis", headers=_sso_headers())
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# What /auth/me reports
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_auth_me_reports_the_effective_role_not_the_token_role(
    client, monkeypatch
):
    """The token says viewer; the group says admin. The UI must hear admin, or
    it will hide the admin nav from someone who can reach the endpoints."""
    await _set_admin_group(ADMIN_GROUP)

    import api.oidc as oidc

    monkeypatch.setattr(oidc, "is_group_member", _member_of(ADMIN_GROUP))
    body = (await client.get("/auth/me", headers=_sso_headers())).json()
    assert body["role"] == "admin"


@pytest.mark.asyncio
async def test_auth_me_still_reports_viewer_for_a_non_member(client, monkeypatch):
    await _set_admin_group(ADMIN_GROUP)

    import api.oidc as oidc

    monkeypatch.setattr(oidc, "is_group_member", _member_of(OTHER_GROUP))
    body = (await client.get("/auth/me", headers=_sso_headers())).json()
    assert body["role"] == "viewer"


@pytest.mark.asyncio
async def test_display_name_is_carried_through_to_the_ui(client):
    body = (
        await client.get("/auth/me", headers=_sso_headers(display_name="Ada Lovelace"))
    ).json()
    assert body["display_name"] == "Ada Lovelace"
    # The UPN is still reported; the sidebar shows both.
    assert body["username"] == "ada@contoso.com"


@pytest.mark.asyncio
async def test_the_upn_is_reported_separately_from_the_account_name(client):
    """The sidebar shows the person, not the account.

    They are different things: ``username`` is whatever signed in, which for
    the local account is literally "admin". A footer reading "Elsie Duarte /
    admin / ADMIN" names the account twice and the person once.
    """
    body = (
        await client.get("/auth/me", headers=_sso_headers(display_name="Ada Lovelace"))
    ).json()
    assert body["upn"] == "ada@contoso.com"


@pytest.mark.asyncio
async def test_the_local_admin_has_no_upn(client):
    """No directory identity, so the footer has only the account name to show."""
    headers = await _local_admin_headers(client)
    body = (await client.get("/auth/me", headers=headers)).json()
    assert body["upn"] is None
    assert body["display_name"] is None
    assert body["username"] == "admin"


@pytest.mark.asyncio
async def test_a_token_issued_before_display_names_still_works(client):
    """Tokens live for hours, so the ones in flight at deploy have no name
    claim. They must resolve, not 500."""
    body = (await client.get("/auth/me", headers=_sso_headers())).json()
    assert body["display_name"] is None
    assert body["username"] == "ada@contoso.com"


# --------------------------------------------------------------------------- #
# Where the display name comes from
# --------------------------------------------------------------------------- #
def test_the_display_name_is_taken_from_the_name_claim_not_the_upn():
    """The bug this replaces: _NAME_CLAIMS took the first of
    preferred_username/upn/email/name, so the UPN always won and the display
    name was thrown away."""
    from api.oidc import _DISPLAY_NAME_CLAIMS, _NAME_CLAIMS

    claims = {"preferred_username": "ada@contoso.com", "name": "Ada Lovelace"}
    upn = next(claims[c] for c in _NAME_CLAIMS if claims.get(c))
    display = next(claims[c] for c in _DISPLAY_NAME_CLAIMS if claims.get(c))
    assert upn == "ada@contoso.com"
    assert display == "Ada Lovelace"
