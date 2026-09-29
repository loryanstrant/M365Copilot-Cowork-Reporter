"""Seed synthetic Cowork data so the dashboards render without live sources.

Idempotent-ish: with ``reset=True`` it clears the fact tables first. Numbers are
plausible but fictional; user names echo the Avanoso demo tenant shape.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete

# Running this as a script ("python scripts/seed_demo.py") puts scripts/ on
# sys.path, not the repo root, so the app's own packages are not importable.
# Add the root explicitly rather than requiring the reader to know to type
# "python -m scripts.seed_demo" — the README tells them the plain form.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.db import SessionLocal
from shared.demo import bind_demo_persona, retire_demo_persona
from shared.migrate import upgrade_to_head
from shared.models import (
    BillingPolicy,
    CoworkEvent,
    CoworkUsage,
    CreditConsumption,
    DailyCost,
    DirectoryUser,
)

_USERS = [
    ("loryan.strant@avanoso.com", "Loryan Strant", "Modern Workplace"),
    ("ping.lim@avanoso.com", "Ping Lim", "Engineering"),
    ("heidi.hasting@avanoso.com", "Heidi Hasting", "Sales"),
    ("bilal.kholki@avanoso.com", "Bilal Kholki", "Finance"),
    ("kevin.silk@avanoso.com", "Kevin Silk", "Engineering"),
    ("patrick.shortt@avanoso.com", "Patrick Shortt", "Consulting"),
]
_RGS = ["rg-copilot-cowork-prod", "rg-copilot-pilot", "rg-shared-ai"]
_METERS = [("Copilot", "Copilot Credits"), ("Azure OpenAI", "gpt tokens")]
_PERIODS = [7, 28, 90, 180]


async def seed(reset: bool = True) -> dict[str, int]:
    # No upgrade_to_head() here. Alembic is synchronous, and this coroutine is
    # awaited straight from the Load demo data endpoint on the API's event
    # loop, so running a full migration chain inside it blocks every other
    # request for its duration. The API and worker already migrate on startup,
    # and the CLI below migrates before it starts the loop, so by the time
    # anything calls this the schema is at head.
    async with SessionLocal() as s:
        if reset:
            for model in (
                DailyCost, CreditConsumption, CoworkUsage, CoworkEvent,
                DirectoryUser, BillingPolicy,
            ):
                await s.execute(delete(model))

        # Directory + chargeback mapping
        for i, (upn, name, dept) in enumerate(_USERS):
            s.add(DirectoryUser(
                user_id=f"user-{i}", upn=upn, email=upn, display_name=name,
                department=dept, account_enabled=True, user_type="Member",
                # Without this the Tenant users page is empty on demo data:
                # it lists only people who are licensed AND in the report data.
                has_copilot_license=True,
            ))
        for i, rg in enumerate(_RGS):
            s.add(BillingPolicy(
                resource_group=rg,
                billing_policy_name=f"BP-{rg.split('-')[-1]}",
                cost_centre=f"CC-{100 + i}", business_owner=_USERS[i][1],
                project=["Cowork Pilot", "AI Platform", "Shared"][i],
            ))

        # Daily cost (rolling 30 days)
        today = date.today()
        cost_rows = 0
        for d in range(30):
            day = today - timedelta(days=d)
            for rg in _RGS:
                for cat, meter in _METERS:
                    s.add(DailyCost(
                        cost_date=day, subscription_id="sub-demo-0001",
                        resource_group=rg, service_name=cat,
                        meter_category=cat, meter_name=meter,
                        cost=round(random.uniform(2, 40), 2), currency="AUD",
                    ))
                    cost_rows += 1

        # Credit consumption snapshot (per user + a Cowork service row)
        credit_rows = 0
        for upn, name, _ in _USERS:
            s.add(CreditConsumption(
                as_of_date=today, scope_type="user", scope_id=upn, scope_name=name,
                license_type="combined",
                credits_consumed=round(random.uniform(50, 800), 1),
                paygo_consumed=round(random.uniform(0, 200), 1),
                last_activity_date=datetime.now(timezone.utc),
            ))
            credit_rows += 1
        s.add(CreditConsumption(
            as_of_date=today, scope_type="service", scope_id="Cowork",
            scope_name="Copilot Cowork", license_type="combined",
            credits_consumed=round(random.uniform(1000, 3000), 1), user_count=len(_USERS),
        ))
        credit_rows += 1

        # Cowork usage snapshot (per user per period)
        usage_rows = 0
        for upn, name, _ in _USERS:
            base = random.randint(1, 12)
            for p in _PERIODS:
                tasks = int(base * (p / 28) * random.uniform(0.6, 1.4))
                s.add(CoworkUsage(
                    report_refresh_date=today, report_period=p,
                    user_principal_name=upn, display_name=name,
                    total_tasks=tasks, scheduled_tasks=random.randint(0, tasks),
                    user_initiated_tasks=tasks, active_days=min(p, random.randint(1, 6)),
                    last_activity_date=datetime.now(timezone.utc)
                    - timedelta(days=random.randint(0, 6)),
                ))
                usage_rows += 1

        # Cowork audit events
        events = 0
        for i in range(40):
            u = random.choice(_USERS)
            when = datetime.now(timezone.utc) - timedelta(
                hours=random.randint(1, 24 * 20)
            )
            s.add(CoworkEvent(
                event_id=f"evt-{i}", created_at=when, user_id="user-x",
                user_principal_name=u[0], operation="CopilotInteraction",
                app_host="cowork", app_identity="Copilot.M365Copilot.CoworkChat",
                agent_name="Copilot Cowork", thread_id=f"19:thread{i}@thread.v2",
                tools=["tool_search_tool"], prompt_message_count=1,
                response_message_count=1,
            ))
            events += 1

        # Bind the local admin to the first seeded user, so the personal pages
        # are reachable without Entra. See shared/demo.py for why.
        upn, name, _dept = _USERS[0]
        await bind_demo_persona(s, user_id="user-0", upn=upn, display_name=name)
        await s.commit()
    return {
        "cost_rows": cost_rows, "credit_rows": credit_rows,
        "usage_rows": usage_rows, "events": events,
        "persona": _USERS[0][0],
    }



async def clear() -> dict[str, int]:
    """Remove all seeded data, leaving credentials and app accounts intact.

    Mirrors the reset list in ``seed`` — fact tables and the chargeback mapping
    only; ``app_config`` and ``app_users`` are never touched.
    """
    async with SessionLocal() as s:
        for model in (
            DailyCost, CreditConsumption, CoworkUsage, CoworkEvent,
            DirectoryUser, BillingPolicy,
        ):
            await s.execute(delete(model))
        # The persona points at a directory row that has just been deleted, so
        # it has to go with it or the personal view resolves to nothing.
        await retire_demo_persona(s)
        await s.commit()
    return {"cleared": 1}


def main() -> int:
    """Command-line entry point, matching the other three solutions."""
    parser = argparse.ArgumentParser(description="Seed or clear Cowork demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing demo rows before seeding (default).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Seed without clearing first, adding to what is already there.",
    )
    parser.add_argument(
        "--clear", action="store_true", help="Clear demo data and exit."
    )
    args = parser.parse_args()

    # psycopg async needs a SelectorEventLoop on Windows (no-op elsewhere).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Only the CLI migrates. The API and worker already do it on startup, and
    # Alembic is synchronous so it must never be called from inside a running
    # event loop — which is what the seed endpoint was doing through seed().
    upgrade_to_head()

    if args.clear:
        asyncio.run(clear())
        print("Demo data cleared.")
        return 0

    stats = asyncio.run(seed(reset=not args.keep))
    print(
        f"Seeded {stats['cost_rows']} cost rows, {stats['events']} events, "
        f"{stats['usage_rows']} usage rows, {stats['credit_rows']} credit rows. "
        f"Personal view bound to {stats['persona']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
