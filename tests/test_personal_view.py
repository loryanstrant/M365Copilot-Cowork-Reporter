"""Personal view and the organisation-view gate.

The security-relevant claims here are:

- a personal endpoint scopes to the caller's own identity, and offers no way to
  ask for somebody else's;
- the organisation view is closed to people outside the configured group;
- but an unconfigured group leaves the org view open, so upgrading an existing
  deployment doesn't lock everyone out.

Cowork facts are keyed two ways: audit events carry the Entra object ID, while
the admin-centre usage export only carries a UPN. Both are seeded here, with
deliberately different casing on the UPN, because casing varies in practice.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import (
    AppConfig,
    AppUser,
    CoworkEvent,
    CoworkUsage,
    CreditConsumption,
    DirectoryUser,
)
from shared.security import hash_password

ME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MY_UPN = "me@contoso.com"
SOMEONE_ELSE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
THEIR_UPN = "them@contoso.com"
GROUP = "cccccccc-cccc-cccc-cccc-cccccccccccc"

REFRESH = date(2026, 9, 1)


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _seed_activity() -> None:
    """Two people with clearly different volumes, so a leak is obvious."""
    async with SessionLocal() as s:
        s.add(DirectoryUser(user_id=ME, upn=MY_UPN, display_name="Me"))
        s.add(DirectoryUser(user_id=SOMEONE_ELSE, upn=THEIR_UPN, display_name="Them"))

        # Usage snapshot keys on UPN. Cased differently from the token on
        # purpose: the admin-centre export and the directory disagree in
        # practice, so the match has to be case-insensitive.
        s.add(
            CoworkUsage(
                report_refresh_date=REFRESH,
                report_period=28,
                user_principal_name="Me@Contoso.com",
                display_name="Me",
                total_tasks=3,
                scheduled_tasks=1,
                user_initiated_tasks=2,
                active_days=2,
            )
        )
        s.add(
            CoworkUsage(
                report_refresh_date=REFRESH,
                report_period=28,
                user_principal_name=THEIR_UPN,
                display_name="Them",
                total_tasks=9,
                scheduled_tasks=4,
                user_initiated_tasks=5,
                active_days=7,
            )
        )

        for i in range(3):
            s.add(
                CoworkEvent(
                    event_id=f"mine-{i}",
                    created_at=datetime(2026, 9, 1, 9, i, tzinfo=timezone.utc),
                    user_id=ME,
                    user_principal_name=MY_UPN,
                    operation="CopilotInteraction",
                    app_host="cowork",
                )
            )
        for i in range(9):
            s.add(
                CoworkEvent(
                    event_id=f"theirs-{i}",
                    created_at=datetime(2026, 9, 1, 10, i, tzinfo=timezone.utc),
                    user_id=SOMEONE_ELSE,
                    user_principal_name=THEIR_UPN,
                    operation="CopilotInteraction",
                    app_host="cowork",
                )
            )

        s.add(
            CreditConsumption(
                as_of_date=REFRESH,
                scope_type="user",
                scope_id=MY_UPN,
                scope_name=MY_UPN,
                credits_consumed=12,
            )
        )
        s.add(
            CreditConsumption(
                as_of_date=REFRESH,
                scope_type="user",
                scope_id=THEIR_UPN,
                scope_name=THEIR_UPN,
                credits_consumed=99,
            )
        )
        await s.commit()


async def _set_org_group(group_id: str | None) -> None:
    async with SessionLocal() as s:
        cfg = await s.get(AppConfig, 1)
        if cfg is None:
            cfg = AppConfig(id=1)
            s.add(cfg)
        cfg.org_view_group_id = group_id
        await s.commit()


def _viewer_headers(oid: str = ME, upn: str = MY_UPN) -> dict[str, str]:
    token = create_access_token(upn, "viewer", oid=oid, upn=upn)
    return {"Authorization": f"Bearer {token}"}


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Personal view
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_personal_summary_counts_only_my_own_activity(client):
    await _seed_activity()
    r = await client.get("/metrics/me/summary", headers=_viewer_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    # Three tasks and three events of mine; nine of theirs. Anything higher is
    # a leak.
    assert body["total_tasks"] == 3
    assert body["cowork_events"] == 3
    assert body["credits_consumed"] == 12
    assert body["has_data"] is True


@pytest.mark.asyncio
async def test_personal_view_cannot_be_pointed_at_someone_else(client):
    """The caller is taken from the token, so a spoofed id changes nothing."""
    await _seed_activity()
    r = await client.get(
        f"/metrics/me/summary?user_id={SOMEONE_ELSE}&upn={THEIR_UPN}"
        f"&user_principal_name={THEIR_UPN}",
        headers=_viewer_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_tasks"] == 3
    assert r.json()["cowork_events"] == 3


@pytest.mark.asyncio
async def test_personal_events_list_only_my_own_sessions(client):
    await _seed_activity()
    r = await client.get("/metrics/me/events", headers=_viewer_headers())
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    assert all(e["event_id"].startswith("mine-") for e in rows)
    assert SOMEONE_ELSE not in r.text
    assert THEIR_UPN not in r.text


@pytest.mark.asyncio
async def test_personal_view_is_absent_without_an_entra_identity(client):
    """The password admin has no object ID, so there is nothing to show them."""
    headers = await _admin_headers(client)
    r = await client.get("/metrics/me/summary", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_comparison_reports_the_median_not_individuals(client):
    await _seed_activity()
    r = await client.get("/metrics/me/comparison", headers=_viewer_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["my_tasks"] == 3
    assert body["people_counted"] == 2
    # No other person's identity should appear anywhere in the payload.
    assert SOMEONE_ELSE not in r.text
    assert THEIR_UPN not in r.text


@pytest.mark.asyncio
async def test_personal_view_requires_authentication(client):
    r = await client.get("/metrics/me/summary")
    assert r.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Organisation-view gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_org_view_open_when_no_group_configured(client):
    """Upgrades must not silently lock existing viewers out."""
    await _seed_activity()
    await _set_org_group(None)
    r = await client.get("/metrics/kpis?days=30", headers=_viewer_headers())
    assert r.status_code == 200, r.text
    assert r.json()["total_tasks"] == 12


@pytest.mark.asyncio
async def test_org_view_denied_to_non_members(client):
    await _seed_activity()
    await _set_org_group(GROUP)
    r = await client.get("/metrics/kpis?days=30", headers=_viewer_headers())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_org_view_allowed_for_group_members(client, monkeypatch):
    await _seed_activity()
    await _set_org_group(GROUP)

    import api.oidc as oidc

    async def _member(principal, group_id, session):
        return group_id == GROUP

    monkeypatch.setattr(oidc, "is_group_member", _member)
    r = await client.get("/metrics/kpis?days=30", headers=_viewer_headers())
    assert r.status_code == 200
    assert r.json()["total_tasks"] == 12


@pytest.mark.asyncio
async def test_admin_bypasses_the_org_group(client):
    await _seed_activity()
    await _set_org_group(GROUP)
    headers = await _admin_headers(client)
    r = await client.get("/metrics/kpis?days=30", headers=headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_personal_view_survives_the_org_gate(client):
    """Losing org access must not cost someone their own data."""
    await _seed_activity()
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (
        await client.get("/metrics/kpis?days=30", headers=headers)
    ).status_code == 403
    r = await client.get("/metrics/me/summary", headers=headers)
    assert r.status_code == 200
    assert r.json()["total_tasks"] == 3


@pytest.mark.asyncio
async def test_auth_me_advertises_capabilities(client):
    await _set_org_group(GROUP)
    r = await client.get("/auth/me", headers=_viewer_headers())
    body = r.json()
    assert body["has_personal_view"] is True
    assert body["can_view_org"] is False


@pytest.mark.asyncio
async def test_shared_lookups_stay_open_to_everyone(client):
    """Freshness and About sit outside the org gate — everyone needs them."""
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (await client.get("/metrics/freshness", headers=headers)).status_code == 200
    assert (await client.get("/metrics/about", headers=headers)).status_code == 200
