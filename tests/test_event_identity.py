"""One event, one identifier: normalising the audit identity onto the directory.

The Purview audit ``UserId`` is not a single identifier. In the same tenant on
the same day it is an Entra object ID for some interactions and a UPN for
others — measured on the live tenant, four of six distinct values were UPNs.
The collector stored whatever it was handed, into both identity columns, and
the consequences were:

* the personal page found nothing, because a person's recent events were all
  stored under their UPN while the page looked them up by object ID;
* most events could not join to ``dim_user`` at all (15 of 80 on that tenant),
  so anything grouped by person under-counted without ever erroring.

The fix has three parts and this file pins all three: the transform stops
writing an object ID into the UPN column, the collector resolves each event's
identifier against the directory before storing it, and — the part that matters
for a tenant with history — every read path finds an event whatever key it was
stored under, so the pages work before any backfill has run.
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
from worker.ingest import resolve_event_identities
from worker.transforms import transform_cowork_event

NOW = datetime.now(timezone.utc)
OID = "fceceeff-5057-4ddf-b1dd-76fb72444ef9"
UPN = "loryan.strant@contoso.com"


def _record(event_id: str, user_id: str, **extra) -> dict:
    return {
        "id": event_id,
        "createdDateTime": NOW.isoformat(),
        "auditData": {
            "UserId": user_id,
            "Operation": "CopilotInteraction",
            "AppIdentity": "Copilot.M365Copilot.CoworkChat",
            "CopilotEventData": {"AppHost": "cowork"},
        },
        **extra,
    }


# --------------------------------------------------------------------------- #
# The transform: shapes are not interchangeable
# --------------------------------------------------------------------------- #
def test_a_upn_audit_id_fills_both_columns():
    row = transform_cowork_event(_record("e1", UPN))
    assert row["user_id"] == UPN
    assert row["user_principal_name"] == UPN


def test_an_object_id_is_never_written_into_the_upn_column():
    """The regression: a column of UPNs that was half object IDs.

    Every read path that joins on UPN had to step over them, and any that
    forgot returned a quietly smaller number.
    """
    row = transform_cowork_event(_record("e1", OID))
    assert row["user_id"] == OID
    assert row["user_principal_name"] is None


def test_an_explicit_upn_on_the_record_is_preferred():
    row = transform_cowork_event(_record("e1", OID, userPrincipalName=UPN))
    assert row["user_id"] == OID
    assert row["user_principal_name"] == UPN


# --------------------------------------------------------------------------- #
# The collector: resolve against the directory before storing
# --------------------------------------------------------------------------- #
async def _directory(user_id: str, upn: str | None) -> None:
    async with SessionLocal() as s:
        s.add(
            DirectoryUser(
                user_id=user_id,
                upn=upn,
                display_name="Ada",
                account_enabled=True,
                user_type="Member",
                has_copilot_license=True,
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_a_upn_keyed_event_is_re_keyed_to_the_object_id():
    await _directory(OID, UPN)
    rows = [transform_cowork_event(_record("e1", UPN))]
    async with SessionLocal() as s:
        await resolve_event_identities(s, rows)
    assert rows[0]["user_id"] == OID
    assert rows[0]["user_principal_name"] == UPN


@pytest.mark.asyncio
async def test_an_object_id_keyed_event_gains_its_upn():
    await _directory(OID, UPN)
    rows = [transform_cowork_event(_record("e1", OID))]
    async with SessionLocal() as s:
        await resolve_event_identities(s, rows)
    assert rows[0]["user_id"] == OID
    assert rows[0]["user_principal_name"] == UPN


@pytest.mark.asyncio
async def test_casing_does_not_prevent_a_match():
    """UPN casing differs between the audit log and the directory."""
    await _directory(OID, UPN)
    rows = [transform_cowork_event(_record("e1", UPN.upper()))]
    async with SessionLocal() as s:
        await resolve_event_identities(s, rows)
    assert rows[0]["user_id"] == OID
    assert rows[0]["user_principal_name"] == UPN


@pytest.mark.asyncio
async def test_an_unmatched_event_is_kept_exactly_as_it_arrived():
    """An event nobody in the directory owns is still an event that happened.

    Someone who has left the tenant, or whom the directory sync has not reached
    yet, has still used Cowork. Dropping the row would quietly remove usage
    from the organisation's totals; keeping it means a later sync can attach it.
    """
    await _directory(OID, UPN)
    rows = [transform_cowork_event(_record("e1", "stranger@elsewhere.com"))]
    async with SessionLocal() as s:
        await resolve_event_identities(s, rows)
    assert rows[0]["user_id"] == "stranger@elsewhere.com"
    assert rows[0]["user_principal_name"] == "stranger@elsewhere.com"


@pytest.mark.asyncio
async def test_the_audit_user_id_wins_when_the_two_columns_name_two_people():
    """A delegated action can carry one person's UserId and another's UPN.

    There is no third answer available here, so the audit UserId is taken —
    it is the field the audit log is keyed on — and both columns are set from
    that one person, rather than leaving a row that names two.
    """
    await _directory(OID, UPN)
    await _directory("other-oid", "bob@contoso.com")
    rows = [
        transform_cowork_event(
            _record("e1", OID, userPrincipalName="bob@contoso.com")
        )
    ]
    async with SessionLocal() as s:
        await resolve_event_identities(s, rows)
    assert rows[0]["user_id"] == OID
    assert rows[0]["user_principal_name"] == UPN


@pytest.mark.asyncio
async def test_resolution_is_idempotent():
    await _directory(OID, UPN)
    rows = [transform_cowork_event(_record("e1", UPN))]
    async with SessionLocal() as s:
        await resolve_event_identities(s, rows)
        before = dict(rows[0])
        await resolve_event_identities(s, rows)
    assert rows[0] == before


# --------------------------------------------------------------------------- #
# The read side: history stored under the old key must still be found
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _token() -> dict[str, str]:
    token = create_access_token("ada", "viewer", oid=OID, upn=UPN)
    return {"Authorization": f"Bearer {token}"}


async def _stored(event_id: str, *, user_id: str | None, upn: str | None, days_ago=1):
    async with SessionLocal() as s:
        s.add(
            CoworkEvent(
                event_id=event_id,
                created_at=NOW - timedelta(days=days_ago),
                user_id=user_id,
                user_principal_name=upn,
                app_host="cowork",
                tools=["search"],
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_an_event_stored_under_a_upn_is_found_for_that_person(client):
    """The bug, pinned.

    A tenant with months of history has events keyed by UPN under a column the
    personal page looks up by object ID. Normalising new rows does not help
    those; they must be found where they are, or the page stays empty until a
    backfill runs.
    """
    await _directory(OID, UPN)
    await _stored("legacy", user_id=UPN, upn=UPN)
    body = (await client.get("/metrics/me/activity", headers=_token())).json()
    assert body["sessions"] == 1
    assert body["has_data"] is True


@pytest.mark.asyncio
async def test_events_under_both_keys_are_counted_once_each(client):
    """The other half of the same tenant's history: a mixture, not a migration.

    Both keys belong to the same person, so the two events are two sessions —
    not one, and not four.
    """
    await _directory(OID, UPN)
    await _stored("old", user_id=UPN, upn=UPN)
    await _stored("new", user_id=OID, upn=UPN)
    body = (await client.get("/metrics/me/activity", headers=_token())).json()
    assert body["sessions"] == 2


@pytest.mark.asyncio
async def test_another_persons_upn_keyed_event_is_not_counted_as_mine(client):
    await _directory(OID, UPN)
    await _directory("other-oid", "bob@contoso.com")
    await _stored("theirs", user_id="bob@contoso.com", upn="bob@contoso.com")
    body = (await client.get("/metrics/me/activity", headers=_token())).json()
    assert body["sessions"] == 0
    assert body["has_data"] is False


# --------------------------------------------------------------------------- #
# The one-off migration over stored rows
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_migration_re_keys_stored_rows_and_leaves_strangers_alone():
    """0007 run against the mixture it was written for."""
    import importlib.util
    from pathlib import Path

    from sqlalchemy import select

    from shared.db import engine

    # Loaded by path: alembic/versions is a script directory, not a package,
    # and the revision filenames start with a digit.
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0007_normalise_event_identity.py"
    )
    spec = importlib.util.spec_from_file_location("_rev_0007", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    await _directory(OID, UPN)
    await _stored("by-upn", user_id=UPN, upn=UPN)
    await _stored("by-oid", user_id=OID, upn=OID)
    await _stored("stranger", user_id="gone@elsewhere.com", upn="gone@elsewhere.com")
    # No object ID at all: addressed by its UPN, because `= NULL` matches
    # nothing on either dialect and this row would otherwise be skipped in
    # silence. It is the branch most likely to rot unnoticed.
    await _stored("no-id", user_id=None, upn=UPN)

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: module._normalise(sync_conn))

    async with SessionLocal() as s:
        rows = {
            r.event_id: (r.user_id, r.user_principal_name)
            for r in (await s.execute(select(CoworkEvent))).scalars()
        }
    assert rows["by-upn"] == (OID, UPN)
    # The object ID was already right; the UPN column held a copy of it.
    assert rows["by-oid"] == (OID, UPN)
    assert rows["stranger"] == ("gone@elsewhere.com", "gone@elsewhere.com")
    assert rows["no-id"] == (OID, UPN)
