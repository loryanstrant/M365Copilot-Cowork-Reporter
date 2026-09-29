"""The demo persona: letting the local admin see the personal pages.

The personal view scopes every query to the signed-in person, taken from their
Entra identity in the token. The local password admin has no Entra identity, so
``has_personal_view`` is false for them and /me is unreachable.

That is correct in production and wrong for evaluation. Anyone trying the app
before wiring up Entra — which is exactly what the README invites them to do,
with a Load demo data button — signs in as the local admin and therefore can
never reach the personal pages the README advertises. The feature appears
broken rather than gated.

So loading demo data binds the local admin to one of the seeded directory
users. The binding is a single row in ``ingest_state``, which already exists to
hold collector bookkeeping and is cleared by the same Clear demo data button
that removes the rows the persona points at.

Two rules keep this from leaking into production:

* It is only ever written by the demo seeder. Nothing in the ingest path
  creates one.
* A successful real ingest deletes it. Otherwise an operator who cuts over to
  live data without pressing Clear demo data keeps seeing a fictional person's
  activity presented as their own — which is worse than stale rows, because it
  is wrong about *whose* data it is.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import IngestState

# Key of the ingest_state row holding the binding. Namespaced so it cannot
# collide with a collector watermark.
DEMO_PERSONA_KEY = "demo:persona"


async def bind_demo_persona(
    session: AsyncSession, *, user_id: str, upn: str, display_name: str | None = None
) -> None:
    """Point the local admin's personal view at a seeded directory user."""
    row = await session.get(IngestState, DEMO_PERSONA_KEY)
    if row is None:
        row = IngestState(key=DEMO_PERSONA_KEY)
        session.add(row)
    row.last_status = "bound"
    row.detail = {"user_id": user_id, "upn": upn, "display_name": display_name}


async def get_demo_persona(session: AsyncSession) -> dict[str, Any] | None:
    """The bound persona, or None when there isn't one."""
    row = await session.scalar(
        select(IngestState).where(IngestState.key == DEMO_PERSONA_KEY)
    )
    if row is None or not row.detail:
        return None
    detail = dict(row.detail)
    return detail if detail.get("user_id") or detail.get("upn") else None


async def retire_demo_persona(session: AsyncSession) -> None:
    """Drop the binding. Called by Clear demo data and by a real ingest."""
    await session.execute(
        delete(IngestState).where(IngestState.key == DEMO_PERSONA_KEY)
    )


__all__ = [
    "DEMO_PERSONA_KEY",
    "bind_demo_persona",
    "get_demo_persona",
    "retire_demo_persona",
]
