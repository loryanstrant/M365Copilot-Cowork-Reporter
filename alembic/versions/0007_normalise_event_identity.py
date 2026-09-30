"""Rewrite historical fact_cowork_event identities to the directory's keys.

``fact_cowork_event.user_id`` holds two different identifiers. The Purview audit
``UserId`` is an Entra object ID on some rows and a UPN on others, in the same
tenant on the same day, and the collector stored whatever it was handed — into
*both* identity columns, so the UPN column ended up holding object IDs as well.
On the tenant this was found in, four of six distinct values were UPNs and only
15 of 80 events could join to ``dim_user`` at all.

The collector now normalises at ingest
(:func:`worker.ingest.resolve_event_identities`). This does the same thing once,
for the rows already stored.

**Why rewrite rather than only match both keys at read time.** The read paths do
match both, and they still will — that is what keeps unmatched rows visible. But
leaving the stored key ambiguous means every future query has to remember the
two-key join, and the one that forgets fails quietly by returning a smaller
number rather than an error. The natural key of a fact table should be one key.
Cleaning it is a one-off; carrying it is forever.

**What it will not do.** A row whose identifier matches no directory user is left
exactly as it is. An event that happened is a fact, and a person who has left the
tenant — or whom the directory sync has not seen yet — still used Cowork. Because
the match is a directory lookup and the target values are already canonical, the
migration is idempotent: running it on a clean table changes nothing.

The rewrite is done in Python over the *distinct* identifier values rather than
in dialect-specific SQL. There are a handful of them however many events there
are (six across eighty rows on the live tenant), so this is a few small UPDATEs,
and it behaves identically on PostgreSQL and SQLite instead of needing a hand-
written variant per dialect that only one of them ever exercises.

Data only; no schema change, so there is nothing to undo.

Revision ID: 0007_normalise_event_identity
Revises: 0006_demo_persona
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_normalise_event_identity"
down_revision = "0006_demo_persona"
branch_labels = None
depends_on = None


def _normalise(bind: sa.engine.Connection) -> int:
    """Re-key events onto the directory. Returns the number of UPDATEs issued."""
    directory: dict[str, tuple[str, str | None]] = {}
    for user_id, upn in bind.execute(
        sa.text("SELECT user_id, upn FROM dim_user")
    ):
        if user_id:
            directory[user_id.lower()] = (user_id, upn)
        if upn:
            directory[upn.lower()] = (user_id, upn)

    pairs = bind.execute(
        sa.text(
            "SELECT DISTINCT user_id, user_principal_name FROM fact_cowork_event"
        )
    ).all()

    set_clause = (
        "UPDATE fact_cowork_event "
        "SET user_id = :new_id, user_principal_name = :new_upn "
    )
    # A row that arrived with no object ID at all is addressed by its UPN, and
    # `= NULL` matches nothing on either dialect — hence the two spellings
    # rather than one predicate that silently updates no rows.
    by_id = sa.text(set_clause + "WHERE user_id = :old_id")
    by_upn = sa.text(
        set_clause + "WHERE user_id IS NULL AND user_principal_name = :old_upn"
    )
    updated = 0
    # One UPDATE per identifier, not per (id, UPN) pair. The same object ID can
    # appear beside several stale spellings of the UPN — which is the mess this
    # exists to clean — and `WHERE user_id = :old_id` already sweeps all of them
    # onto the same canonical values. Without this the later pairs re-issue an
    # UPDATE that changes nothing and the returned count stops meaning anything.
    done: set[tuple[str | None, str | None]] = set()
    for old_id, old_upn in pairs:
        key = (old_id, None if old_id is not None else old_upn)
        if key in done:
            continue
        done.add(key)
        match = next(
            (
                directory[str(key).lower()]
                for key in (old_id, old_upn)
                if key and str(key).lower() in directory
            ),
            None,
        )
        if match is None:
            continue
        new_id, new_upn = match
        new_upn = new_upn or old_upn
        if new_id == old_id and new_upn == old_upn:
            continue
        params = {"new_id": new_id, "new_upn": new_upn}
        if old_id is None:
            bind.execute(by_upn, {**params, "old_upn": old_upn})
        else:
            bind.execute(by_id, {**params, "old_id": old_id})
        updated += 1
    return updated


def upgrade() -> None:
    _normalise(op.get_bind())


def downgrade() -> None:
    # Irreversible by nature: the original mixed identifiers are not recorded
    # anywhere to put back. The read paths match on either key, so a database
    # rolled back to 0006 still reads normalised rows correctly.
    pass
