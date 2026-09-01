"""Reporting/metrics routes (any authenticated user).

Consumption and Usage are exposed as separate resources and never blended into a
single measure — they join on user, not on resource group (dollars vs task counts).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.schemas import (
    CostByGroupOut,
    CostTrendOut,
    KpiOut,
    UsageByUserOut,
    UsageTrendOut,
)
from shared.db import get_session
from shared.models import (
    BillingPolicy,
    CoworkEvent,
    CoworkUsage,
    CreditConsumption,
    DailyCost,
    DirectoryUser,
)

router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)]
)


def _default_window(days: int) -> date:
    return date.today() - timedelta(days=days)


# --- headline KPIs ------------------------------------------------------
@router.get("/kpis", response_model=KpiOut)
async def kpis(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> KpiOut:
    since = _default_window(days)

    total_cost = await session.scalar(
        select(func.coalesce(func.sum(DailyCost.cost), 0)).where(
            DailyCost.cost_date >= since
        )
    ) or 0
    currency = await session.scalar(
        select(DailyCost.currency).where(DailyCost.currency.isnot(None)).limit(1)
    )
    # Latest credit snapshot total (credits don't sum across snapshots).
    latest_as_of = await session.scalar(select(func.max(CreditConsumption.as_of_date)))
    total_credits = 0
    if latest_as_of is not None:
        total_credits = await session.scalar(
            select(func.coalesce(func.sum(CreditConsumption.credits_consumed), 0)).where(
                CreditConsumption.as_of_date == latest_as_of,
                CreditConsumption.scope_type == "user",
            )
        ) or 0
        if not total_credits:  # fall back to whatever scope was uploaded
            total_credits = await session.scalar(
                select(func.coalesce(func.sum(CreditConsumption.credits_consumed), 0)).where(
                    CreditConsumption.as_of_date == latest_as_of
                )
            ) or 0

    # Usage: latest snapshot for the closest matching period.
    latest_refresh = await session.scalar(select(func.max(CoworkUsage.report_refresh_date)))
    total_tasks = 0
    active_users = 0
    if latest_refresh is not None:
        period = await _closest_period(session, latest_refresh, days)
        total_tasks = await session.scalar(
            select(func.coalesce(func.sum(CoworkUsage.total_tasks), 0)).where(
                CoworkUsage.report_refresh_date == latest_refresh,
                CoworkUsage.report_period == period,
            )
        ) or 0
        active_users = await session.scalar(
            select(func.count()).select_from(CoworkUsage).where(
                CoworkUsage.report_refresh_date == latest_refresh,
                CoworkUsage.report_period == period,
                CoworkUsage.total_tasks > 0,
            )
        ) or 0

    events = await session.scalar(
        select(func.count()).select_from(CoworkEvent).where(
            CoworkEvent.created_at.isnot(None)
        )
    ) or 0

    return KpiOut(
        total_cost=float(total_cost),
        currency=currency,
        total_credits=float(total_credits),
        total_tasks=int(total_tasks),
        active_users=int(active_users),
        cowork_events=int(events),
    )


async def _closest_period(session: AsyncSession, refresh: date, days: int) -> int | None:
    """Pick the report_period nearest to the requested window."""
    periods = (
        await session.execute(
            select(CoworkUsage.report_period)
            .where(CoworkUsage.report_refresh_date == refresh)
            .distinct()
        )
    ).scalars().all()
    periods = [p for p in periods if p is not None]
    if not periods:
        return None
    return min(periods, key=lambda p: abs(p - days))


# --- CONSUMPTION --------------------------------------------------------
@router.get("/cost/by-group", response_model=list[CostByGroupOut])
async def cost_by_group(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> list[CostByGroupOut]:
    """Azure cost grouped by resource group, joined to the chargeback mapping."""
    since = _default_window(days)
    stmt = (
        select(
            DailyCost.resource_group,
            BillingPolicy.cost_centre,
            BillingPolicy.project,
            func.sum(DailyCost.cost).label("cost"),
        )
        .select_from(DailyCost)
        .join(
            BillingPolicy,
            BillingPolicy.resource_group == DailyCost.resource_group,
            isouter=True,
        )
        .where(DailyCost.cost_date >= since)
        .group_by(DailyCost.resource_group, BillingPolicy.cost_centre, BillingPolicy.project)
        .order_by(func.sum(DailyCost.cost).desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        CostByGroupOut(
            resource_group=r.resource_group,
            cost_centre=r.cost_centre,
            project=r.project,
            cost=float(r.cost or 0),
        )
        for r in rows
    ]


@router.get("/cost/trend", response_model=list[CostTrendOut])
async def cost_trend(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> list[CostTrendOut]:
    since = _default_window(days)
    stmt = (
        select(DailyCost.cost_date, func.sum(DailyCost.cost).label("cost"))
        .where(DailyCost.cost_date >= since)
        .group_by(DailyCost.cost_date)
        .order_by(DailyCost.cost_date)
    )
    rows = (await session.execute(stmt)).all()
    return [CostTrendOut(cost_date=r.cost_date, cost=float(r.cost or 0)) for r in rows]


# --- USAGE --------------------------------------------------------------
@router.get("/usage/by-user", response_model=list[UsageByUserOut])
async def usage_by_user(
    period: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> list[UsageByUserOut]:
    """Per-user Cowork adoption for the latest snapshot, enriched with department."""
    latest_refresh = await session.scalar(select(func.max(CoworkUsage.report_refresh_date)))
    if latest_refresh is None:
        return []
    if period is None:
        period = await _closest_period(session, latest_refresh, 28)

    stmt = (
        select(CoworkUsage, DirectoryUser.department)
        .select_from(CoworkUsage)
        .join(
            DirectoryUser,
            func.lower(DirectoryUser.upn) == func.lower(CoworkUsage.user_principal_name),
            isouter=True,
        )
        .where(
            CoworkUsage.report_refresh_date == latest_refresh,
            CoworkUsage.report_period == period,
        )
        .order_by(CoworkUsage.total_tasks.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        UsageByUserOut(
            user_principal_name=u.user_principal_name,
            display_name=u.display_name,
            department=dept,
            total_tasks=u.total_tasks,
            scheduled_tasks=u.scheduled_tasks,
            user_initiated_tasks=u.user_initiated_tasks,
            active_days=u.active_days,
            last_activity_date=u.last_activity_date,
        )
        for (u, dept) in rows
    ]


@router.get("/usage/trend", response_model=list[UsageTrendOut])
async def usage_trend(
    session: AsyncSession = Depends(get_session),
) -> list[UsageTrendOut]:
    """Active users + total tasks by report period for the latest snapshot."""
    latest_refresh = await session.scalar(select(func.max(CoworkUsage.report_refresh_date)))
    if latest_refresh is None:
        return []
    stmt = (
        select(
            CoworkUsage.report_period,
            func.count().filter(CoworkUsage.total_tasks > 0).label("active_users"),
            func.coalesce(func.sum(CoworkUsage.total_tasks), 0).label("total_tasks"),
        )
        .where(
            CoworkUsage.report_refresh_date == latest_refresh,
            CoworkUsage.report_period.isnot(None),
        )
        .group_by(CoworkUsage.report_period)
        .order_by(CoworkUsage.report_period)
    )
    rows = (await session.execute(stmt)).all()
    return [
        UsageTrendOut(
            period_days=r.report_period,
            active_users=int(r.active_users or 0),
            total_tasks=int(r.total_tasks or 0),
        )
        for r in rows
    ]
