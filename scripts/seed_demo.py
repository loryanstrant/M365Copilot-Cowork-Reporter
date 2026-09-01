"""Seed synthetic Cowork data so the dashboards render without live sources.

Idempotent-ish: with ``reset=True`` it clears the fact tables first. Numbers are
plausible but fictional; user names echo the Avanoso demo tenant shape.
"""
from __future__ import annotations

import asyncio
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete

from shared.db import SessionLocal
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
    upgrade_to_head()
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

        await s.commit()
    return {
        "cost_rows": cost_rows, "credit_rows": credit_rows,
        "usage_rows": usage_rows, "events": events,
    }


if __name__ == "__main__":
    print(asyncio.run(seed()))
