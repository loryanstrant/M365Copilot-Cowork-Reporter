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

from scripts._demo_tenant import DOMAIN
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
    JobRun,
)

# The named people from the Avanoso demo tenant shape. They stay, and they stay
# first, because two things depend on them: the chargeback mapping names the
# first three as business owners, and the demo persona binds the local admin to
# index 0 so the personal pages are reachable without Entra.
_NAMED_USERS = [
    (f"loryan.strant@{DOMAIN}", "Loryan Strant"),
    (f"ping.lim@{DOMAIN}", "Ping Lim"),
    (f"heidi.hasting@{DOMAIN}", "Heidi Hasting"),
    (f"bilal.kholki@{DOMAIN}", "Bilal Kholki"),
    (f"kevin.silk@{DOMAIN}", "Kevin Silk"),
    (f"patrick.shortt@{DOMAIN}", "Patrick Shortt"),
]

# Six people was a fixture from before there was anything to compare. The
# personal page now withholds the team series below five peers — a disclosure
# rule, because a team average plus your own figure gives a colleague's number
# away — and the biggest department here held three. So the comparison the demo
# exists to demonstrate never appeared at all on a fresh instance.
#
# The fix is a representative population rather than a lower threshold:
# ninety people across six departments, assigned round-robin. Random assignment
# does not do it — with ninety people and six departments, chance alone
# regularly leaves one department under the floor, and a demo whose key panel
# is missing one run in five is worse than one that is always missing it,
# because nobody believes it is broken.
_DEMO_PEOPLE = 90

_DEPARTMENTS = [
    "Modern Workplace",
    "Finance",
    "Engineering",
    "Sales",
    "Professional Services",
    "People & Culture",
]

# Deterministic synthetic names, so two seed runs produce the same tenant and a
# screenshot taken today matches one taken next week.
_FIRST_NAMES = [
    "Ada", "Blair", "Casey", "Devi", "Elif", "Farid", "Grace", "Hana",
    "Ibrahim", "Jun", "Kira", "Lachlan", "Mei", "Niamh", "Omar", "Priya",
    "Quinn", "Rafael", "Sanne", "Tomas",
]
_LAST_NAMES = [
    "Abbott", "Byrne", "Costa", "Dube", "Eriksen", "Fontaine", "Gallo",
    "Haddad", "Ivanov", "Jensen", "Kaur", "Lindqvist", "Moreau", "Nakamura",
    "Okafor", "Pereira", "Quill", "Ruiz", "Sandoval", "Tanaka",
]


def _population(count: int = _DEMO_PEOPLE) -> list[tuple[str, str, str, str]]:
    """``(upn, display_name, department, manager_name)`` for the demo tenant.

    Departments are dealt round-robin across the whole list, named people
    included, so every department lands the same size and every one of them
    clears the comparison's peer floor. Each department's first member is its
    manager, which gives the manager fallback a group to find as well — it is
    the path taken when a tenant populates managers but not departments, and
    it was previously unexercised by any demo data.
    """
    people: list[tuple[str, str, str, str]] = []
    for i in range(max(count, len(_NAMED_USERS))):
        if i < len(_NAMED_USERS):
            upn, name = _NAMED_USERS[i]
        else:
            first = _FIRST_NAMES[i % len(_FIRST_NAMES)]
            last = _LAST_NAMES[(i // len(_FIRST_NAMES)) % len(_LAST_NAMES)]
            name = f"{first} {last}"
            upn = f"{first.lower()}.{last.lower()}{i}@{DOMAIN}"
        dept = _DEPARTMENTS[i % len(_DEPARTMENTS)]
        people.append((upn, name, dept, ""))

    # The first person dealt into each department manages it.
    leads: dict[str, str] = {}
    for _upn, name, dept, _mgr in people:
        leads.setdefault(dept, name)
    return [
        (upn, name, dept, leads[dept] if leads[dept] != name else "")
        for upn, name, dept, _mgr in people
    ]


_USERS = _population()
_RGS = ["rg-copilot-cowork-prod", "rg-copilot-pilot", "rg-shared-ai"]
_METERS = [("Copilot", "Copilot Credits"), ("Azure OpenAI", "gpt tokens")]
_PERIODS = [7, 28, 90, 180]
# Named tools and documents, so the "top tools" bars have something to rank.
#
# Agents are not part of that any more. Cowork reports itself, so the seeder's
# cast of Researcher, Analyst, Facilitator and friends made a breakdown look
# meaningful that against a real tenant ranked one name against itself — which
# is why that breakdown is gone and this list has one entry.
_AGENTS = ["Copilot Cowork"]
_TOOLS = [
    "file_search", "web_search", "create_document", "send_mail",
    "summarise_thread", "schedule_meeting", "code_interpreter",
]
_FILES = [
    "FY27 budget.xlsx", "Board pack.pptx", "Customer health.docx",
    "Migration plan.docx", "Pricing model.xlsx", "Roadmap.pptx",
]


def _seed_job_runs(s) -> int:
    """A fortnight of collection runs, for the Scan history page.

    Nothing seeded ``job_runs`` before, so Scan history opened empty on a fresh
    instance and read as a broken page rather than a new one.

    The fortnight includes a failure, because a run log where everything always
    succeeded teaches nobody what a failure looks like — which is the single
    thing the page exists to make findable. It also includes both ``csv-*``
    kinds, which are this app's alone and therefore the two most likely to be
    rendered wrongly by a label table copied from a sibling, and one run still
    in progress so all three status shapes appear (● ◐ ○).

    Stats are written in the shape the real collectors write them — nested per
    collector for an ingest, flat for an upload — so the page's flattening is
    exercised rather than assumed.
    """
    now = datetime.now(timezone.utc)
    rows = 0

    def add(*, name: str, status: str, started: datetime, seconds: int | None,
            stats: dict | None) -> None:
        nonlocal rows
        s.add(JobRun(
            job_name=name, status=status, started_at=started,
            finished_at=started + timedelta(seconds=seconds) if seconds else None,
            stats=stats,
        ))
        rows += 1

    # Fourteen nightly collections at 02:10, most of them fine.
    for d in range(14, 0, -1):
        started = (now - timedelta(days=d)).replace(hour=2, minute=10, second=0)
        if d == 4:
            add(
                name="scheduled", status="failed", started=started, seconds=38,
                stats={
                    "users": {"users": len(_USERS), "copilot_licensed": len(_USERS)},
                    "error": "Graph throttled the audit query (429) after 5 retries",
                },
            )
            continue
        add(
            name="scheduled", status="success", started=started,
            seconds=random.randint(70, 260),
            stats={
                "users": {"users": len(_USERS), "copilot_licensed": len(_USERS)},
                "cost": {"subscriptions": 1, "rows": 6 * len(_RGS), "window_days": 30},
                "audit": {
                    "scanned": random.randint(400, 900),
                    "cowork_events": random.randint(20, 80),
                },
            },
        )

    # The two upload kinds no other report in the suite has.
    add(
        name="csv-cowork-usage", status="success",
        started=now - timedelta(days=9, hours=3), seconds=4,
        stats={"rows": 90, "imported": 88, "skipped": 2},
    )
    add(
        name="csv-credit-consumption", status="success",
        started=now - timedelta(days=9, hours=2), seconds=3,
        stats={"rows": 91, "imported": 91, "skipped": 0, "scope_type": "user"},
    )

    # Someone pressing Run now, and a backfill that was called off part way.
    add(
        name="manual", status="success", started=now - timedelta(days=6, hours=5),
        seconds=142,
        stats={
            "users": {"users": len(_USERS), "copilot_licensed": len(_USERS)},
            "cost": {"subscriptions": 1, "rows": 6 * len(_RGS), "window_days": 30},
            "audit": {"scanned": 610, "cowork_events": 44},
        },
    )
    add(
        name="backfill", status="cancelled", started=now - timedelta(days=11),
        seconds=2_400,
        stats={
            "windows": 12, "windows_done": 7, "scanned": 5_400,
            "cowork_events": 430,
            "from": (now - timedelta(days=180)).date().isoformat(),
            "to": now.date().isoformat(),
        },
    )
    # Still going, so the in-progress indicator is on screen too. A backfill
    # legitimately runs for a long time, which is why it is this kind and not a
    # nightly collection that would look stuck.
    add(
        name="backfill", status="running", started=now - timedelta(minutes=3),
        seconds=None, stats={"windows": 12, "windows_done": 2},
    )
    return rows


async def seed(reset: bool = True) -> dict[str, int]:
    # No upgrade_to_head() here. Alembic is synchronous, and this coroutine is
    # awaited straight from the Load demo data endpoint on the API's event
    # loop, so running a full migration chain inside it blocks every other
    # request for its duration. The API and worker already migrate on startup,
    # and the CLI below migrates before it starts the loop, so by the time
    # anything calls this the schema is at head.
    async with SessionLocal() as s:
        if reset:
            # JobRun is in this list, so Load demo data replaces the run
            # history rather than mixing eighteen fictional runs in with any
            # real ones. Loading demo data is already destructive to every
            # other fact table for the same reason.
            for model in (
                DailyCost, CreditConsumption, CoworkUsage, CoworkEvent,
                DirectoryUser, BillingPolicy, JobRun,
            ):
                await s.execute(delete(model))

        # Directory + chargeback mapping
        for i, (upn, name, dept, manager) in enumerate(_USERS):
            s.add(DirectoryUser(
                user_id=f"user-{i}", upn=upn, email=upn, display_name=name,
                department=dept, manager_name=manager or None,
                account_enabled=True, user_type="Member",
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
        for upn, name, *_ in _USERS:
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
        for upn, name, *_ in _USERS:
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
        # Volume is now per person rather than a flat total shared out at
        # random. With ninety people, a fixed 420 events gave everyone four or
        # five and the persona's own page had almost nothing on it — the page
        # the demo persona exists to show. So each person gets their own
        # activity level, and the persona is deliberately one of the busiest,
        # which is also what makes their percentile worth looking at.
        events = 0
        for idx, (upn, *_rest) in enumerate(_USERS):
            per_person = 48 if idx == 0 else random.randint(4, 22)
            for n in range(per_person):
                # Weight recent days more heavily, so the per-day chart has a
                # shape rather than a flat random scatter. Quiet days are left
                # quiet: the timeline draws them as empty slots, and a
                # fortnight of silence is usually the useful signal.
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
                    event_id=f"evt-{idx}-{n}", created_at=when, user_id=f"user-{idx}",
                    user_principal_name=upn, operation="CopilotInteraction",
                    app_host="cowork", app_identity="Copilot.M365Copilot.CoworkChat",
                    agent_name=agent, thread_id=f"19:thread{idx}-{n}@thread.v2",
                    tools=tools, accessed_resources=files,
                    prompt_message_count=random.randint(1, 4),
                    response_message_count=random.randint(1, 4),
                ))
                events += 1

        job_rows = _seed_job_runs(s)

        # Bind the local admin to the first seeded user, so the personal pages
        # are reachable without Entra. See shared/demo.py for why.
        await bind_demo_persona(s, user_id="user-0")
        await s.commit()
    return {
        "cost_rows": cost_rows, "credit_rows": credit_rows,
        "usage_rows": usage_rows, "events": events,
        "job_rows": job_rows, "people": len(_USERS),
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
            DirectoryUser, BillingPolicy, JobRun,
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
        f"Seeded {stats['people']} people, {stats['cost_rows']} cost rows, "
        f"{stats['events']} events, {stats['usage_rows']} usage rows, "
        f"{stats['credit_rows']} credit rows, {stats['job_rows']} collection runs. "
        f"Personal view bound to {stats['persona']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
