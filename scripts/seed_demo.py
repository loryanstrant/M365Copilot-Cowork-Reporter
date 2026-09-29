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

# Departments deliberately repeat. The personal page compares you against your
# team, and with one person per department every "team" was a team of one whose
# median was your own figure — a comparison that looks broken because it is
# comparing you with yourself.
_USERS = [
    ("loryan.strant@avanoso.com", "Loryan Strant", "Modern Workplace"),
    ("ping.lim@avanoso.com", "Ping Lim", "Modern Workplace"),
    ("heidi.hasting@avanoso.com", "Heidi Hasting", "Modern Workplace"),
    ("bilal.kholki@avanoso.com", "Bilal Kholki", "Finance"),
    ("kevin.silk@avanoso.com", "Kevin Silk", "Engineering"),
    ("patrick.shortt@avanoso.com", "Patrick Shortt", "Engineering"),
]
_RGS = ["rg-copilot-cowork-prod", "rg-copilot-pilot", "rg-shared-ai"]
_METERS = [("Copilot", "Copilot Credits"), ("Azure OpenAI", "gpt tokens")]
_PERIODS = [7, 28, 90, 180]
# Named agents, tools and documents, so the "top agents" and "top tools" bars
# have something to rank. The old seeder used one agent and one tool, which
# rendered as a single bar and demonstrated nothing.
_AGENTS = [
    "Researcher", "Analyst", "Facilitator", "Writer", "Scheduler", "Copilot Cowork",
]
_TOOLS = [
    "file_search", "web_search", "create_document", "send_mail",
    "summarise_thread", "schedule_meeting", "code_interpreter",
]
_FILES = [
    "FY27 budget.xlsx", "Board pack.pptx", "Customer health.docx",
    "Migration plan.docx", "Pricing model.xlsx", "Roadmap.pptx",
]


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

        # Daily cost. 75 days for the same reason the events span 75: the
        # briefing compares the last 30 days against the 30 before them, and
        # cost confined to the recent window shows no change at all. Spend is
        # scaled up slightly in the recent half so the comparison has a
        # direction rather than being noise either side of a flat line.
        today = date.today()
        cost_rows = 0
        for d in range(75):
            day = today - timedelta(days=d)
            scale = 1.0 if d < 30 else 0.7
            for rg in _RGS:
                for cat, meter in _METERS:
                    s.add(DailyCost(
                        cost_date=day, subscription_id="sub-demo-0001",
                        resource_group=rg, service_name=cat,
                        meter_category=cat, meter_name=meter,
                        cost=round(random.uniform(2, 40) * scale, 2), currency="AUD",
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

        # Cowork audit events.
        #
        # Spread over 75 days on purpose. The executive briefing compares the
        # last 30 days with the 30 before them, so demo data confined to the
        # recent window makes every change read "new this period" and the
        # screen cannot demonstrate what it is for.
        #
        # user_id is the directory user's real id. It used to be the constant
        # "user-x", which matched nobody in dim_user, so anything joining
        # events to the directory by object id silently found nothing.
        events = 0
        for i in range(420):
            idx = random.randrange(len(_USERS))
            upn, _name, _dept = _USERS[idx]
            # Weight recent days more heavily, so the per-day chart has a shape
            # rather than a flat random scatter.
            day = min(int(abs(random.gauss(0, 26))), 74)
            when = datetime.now(timezone.utc) - timedelta(
                days=day, hours=random.randint(0, 23), minutes=random.randint(0, 59)
            )
            agent = random.choice(_AGENTS)
            tools = random.sample(_TOOLS, random.randint(1, 4))
            files = [
                {"id": f"file-{random.randint(1, 400)}", "name": random.choice(_FILES)}
                for _ in range(random.randint(0, 5))
            ]
            s.add(CoworkEvent(
                event_id=f"evt-{i}", created_at=when, user_id=f"user-{idx}",
                user_principal_name=upn, operation="CopilotInteraction",
                app_host="cowork", app_identity="Copilot.M365Copilot.CoworkChat",
                agent_name=agent, thread_id=f"19:thread{i}@thread.v2",
                tools=tools, accessed_resources=files,
                prompt_message_count=random.randint(1, 4),
                response_message_count=random.randint(1, 4),
            ))
            events += 1

        # Bind the local admin to the first seeded user, so the personal pages
        # are reachable without Entra. See shared/demo.py for why.
        await bind_demo_persona(s, user_id="user-0")
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
