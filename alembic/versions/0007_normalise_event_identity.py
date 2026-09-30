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
    """Re-key events onto the directory.

    Returns the number of UPDATE statements issued — one per distinct stored
    (user_id, user_principal_name) pair that needed changing, which is not the
    same as the number of rows affected.
    """
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

    # Each statement addresses **exactly** the pair it was derived from, never
    # just one half of it. Matching on `user_id` alone would be enough for the
    # data this was written for and wrong in general: an object ID that appears
    # beside two different UPNs would have every one of its rows swept onto
    # whichever of the two happened to be resolved first. The identifiers here
    # are inconsistent by assumption — that is the whole premise — so the
    # migration does not get to assume one of them is reliable on its own.
    #
    # `= NULL` matches nothing on either dialect, so a NULL on either side
    # needs `IS NULL` rather than a bind parameter, and the predicate is built
    # per pair instead of spelled once.
    updated = 0
    for old_id, old_upn in pairs:
        match = next(
            (
                directory[str(candidate).lower()]
                for candidate in (old_id, old_upn)
                if candidate and str(candidate).lower() in directory
            ),
            None,
        )
        if match is None:
            continue
        new_id, new_upn = match
        new_upn = new_upn or old_upn
        if new_id == old_id and new_upn == old_upn:
            continue

        params: dict[str, object] = {"new_id": new_id, "new_upn": new_upn}
        where = []
        if old_id is None:
            where.append("user_id IS NULL")
        else:
            where.append("user_id = :old_id")
            params["old_id"] = old_id
        if old_upn is None:
            where.append("user_principal_name IS NULL")
        else:
            where.append("user_principal_name = :old_upn")
            params["old_upn"] = old_upn

        bind.execute(
            sa.text(
                "UPDATE fact_cowork_event "
                "SET user_id = :new_id, user_principal_name = :new_upn "
                "WHERE " + " AND ".join(where)
            ),
            params,
        )
        updated += 1
    return updated


def upgrade() -> None:
    _normalise(op.get_bind())


def downgrade() -> None:
    # Irreversible by nature: the original mixed identifiers are not recorded
    # anywhere to put back. The read paths match on either key, so a database
    # rolled back to 0006 still reads normalised rows correctly.
    pass
