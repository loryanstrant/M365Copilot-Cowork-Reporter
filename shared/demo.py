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
users. The binding is ``app_config.demo_persona_user_id``: a nullable column
sitting with the rest of the configuration, rather than a row squatting in
``ingest_state``, which is a table of collector watermarks and would hide an
identity binding somewhere nobody reading the model would find it.

Two rules keep this from leaking into production:

* It is only ever written by the demo seeder. Nothing in the ingest path
  creates one.
* A successful real ingest clears it. Otherwise an operator who cuts over to
  live data without pressing Clear demo data keeps seeing a fictional person's
  activity presented as their own — which is worse than stale rows, because it
  is wrong about *whose* data it is.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import AppConfig


async def bind_demo_persona(session: AsyncSession, *, user_id: str) -> None:
    """Point the local admin's personal view at a seeded directory user."""
    cfg = await session.get(AppConfig, 1)
    if cfg is None:
        cfg = AppConfig(id=1, azure_subscription_ids=[])
        session.add(cfg)
    cfg.demo_persona_user_id = user_id


async def get_demo_persona_user_id(session: AsyncSession) -> str | None:
    """The bound directory user id, or None when nothing is bound."""
    cfg = await session.get(AppConfig, 1)
    return (cfg.demo_persona_user_id if cfg else None) or None


async def retire_demo_persona(session: AsyncSession) -> None:
    """Drop the binding. Called by Clear demo data and by a real ingest."""
    cfg = await session.get(AppConfig, 1)
    if cfg is not None:
        cfg.demo_persona_user_id = None


__all__ = [
    "bind_demo_persona",
    "get_demo_persona_user_id",
    "retire_demo_persona",
]
