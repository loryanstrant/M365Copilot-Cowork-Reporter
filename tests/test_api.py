"""API smoke tests via ASGI transport (auth + metrics + upload)."""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from shared.db import SessionLocal
from shared.models import AppUser
from shared.security import hash_password


@pytest_asyncio.fixture
async def client():
    # Seed an admin user directly.
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()

    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _token(client: httpx.AsyncClient) -> str:
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] is True


@pytest.mark.asyncio
async def test_login_and_status(client):
    token = await _token(client)
    hdr = {"Authorization": f"Bearer {token}"}
    r = await client.get("/admin/status", headers=hdr)
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["cowork_events"] == 0


@pytest.mark.asyncio
async def test_kpis_empty(client):
    token = await _token(client)
    hdr = {"Authorization": f"Bearer {token}"}
    r = await client.get("/metrics/kpis?days=30", headers=hdr)
    assert r.status_code == 200
    assert r.json()["total_cost"] == 0


@pytest.mark.asyncio
async def test_upload_cowork_usage_and_query(client):
    token = await _token(client)
    hdr = {"Authorization": f"Bearer {token}"}
    csv = (
        "User Principal Name,Display Name,Total Tasks,Scheduled Tasks,"
        "User-initiated Tasks,Active Days,Last Activity Date\n"
        "loryan.strant@avanoso.com,Loryan,8,0,8,3,2026-08-26\n"
    )
    r = await client.post(
        "/admin/upload/cowork-usage",
        headers=hdr,
        files={"file": ("usage.csv", csv, "text/csv")},
        data={"report_period": "28"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1

    r2 = await client.get("/metrics/usage/by-user?period=28", headers=hdr)
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["total_tasks"] == 8


@pytest.mark.asyncio
async def test_billing_policy_crud(client):
    token = await _token(client)
    hdr = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        "/admin/billing-policies",
        headers=hdr,
        json={"resource_group": "RG-Cowork", "cost_centre": "CC-100"},
    )
    assert r.status_code == 200
    assert r.json()["resource_group"] == "rg-cowork"  # normalised
    r2 = await client.get("/admin/billing-policies", headers=hdr)
    assert len(r2.json()) == 1
