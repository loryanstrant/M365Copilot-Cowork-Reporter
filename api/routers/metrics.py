"""Reporting/metrics routes.

Consumption and Usage are exposed as separate resources and never blended into a
single measure — they join on user, not on resource group (dollars vs task counts).

Routes are split by who may see what:

``router`` — organisation-wide data. Gated by :func:`require_org_view`, so it
needs both a valid token and membership of the configured organisation-view
group (admins always pass).

``common_router`` — data any signed-in user may see regardless of that group:
data freshness and build info.

``me_router`` — the personal view. Every route derives the person from the
token, never from a client-supplied id, so one user cannot read another's data
by editing a URL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, case, func, literal, or_, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import GenericFunction
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import (
    CurrentUser,
    get_current_user,
    personal_view_user_id,
    require_org_view,
)
from api.schemas import (
    BriefingDeltaOut,
    BriefingItemOut,
    BriefingOut,
    CostByGroupOut,
    CostTrendOut,
    DirectoryUserOut,
    KpiOut,
    MyActivityOut,
    MyComparisonOut,
    MyDayOut,
    MyEventOut,
    MyStandingOut,
    MyTopItemOut,
    PeerStatOut,
    MySummaryOut,
    MyUsageTrendOut,
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
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(require_org_view)]
)

common_router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)]
)

me_router = APIRouter(prefix="/metrics/me", tags=["metrics", "personal"])


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
        select(CoworkUsage, DirectoryUser)
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
            department=du.department if du else None,
            job_title=du.job_title if du else None,
            company_name=du.company_name if du else None,
            office_location=du.office_location if du else None,
            country=du.country if du else None,
            manager_name=du.manager_name if du else None,
            total_tasks=u.total_tasks,
            scheduled_tasks=u.scheduled_tasks,
            user_initiated_tasks=u.user_initiated_tasks,
            active_days=u.active_days,
            last_activity_date=u.last_activity_date,
        )
        for (u, du) in rows
    ]


@router.get("/users", response_model=list[DirectoryUserOut])
async def directory_users(
    session: AsyncSession = Depends(get_session),
) -> list[DirectoryUserOut]:
    """The people this report is actually about: licensed, and in the data.

    A directory dump is not a useful answer here. A tenant's dim_user holds
    every member Graph returned — most of whom have no Copilot licence and
    appear nowhere in any Cowork report — so listing them all buries the few
    hundred rows anyone came to look at under a few thousand they did not.

    So a row must be both:

    * **licensed** — has_copilot_license is true. Note this is `is True`, not
      truthiness: NULL means "never determined" (see migration 0005) and must
      not pass as licensed on the strength of not being False.
    * **present in the report data** — matched in fact_cowork_usage or
      fact_cowork_event.

    People with a licence and no activity are the rows worth finding, so
    "present in the data" deliberately does not mean "did something". A person
    matched with zero tasks and zero sessions is exactly the row that answers
    "who are we paying for and not getting anything from", and it is listed
    with its zeroes rather than filtered out.

    UPN casing differs between the directory and the admin-centre exports, so
    every join is on lower(upn). Audit events carry the Entra object ID as well,
    which the directory join uses in preference where present.
    """
    # Aggregate each fact stream per person first, so the outer query stays one
    # row per user however many snapshots or events they have.
    usage = (
        select(
            func.lower(CoworkUsage.user_principal_name).label("upn"),
            func.coalesce(func.sum(CoworkUsage.total_tasks), 0).label("total_tasks"),
            func.max(CoworkUsage.last_activity_date).label("last_activity_date"),
        )
        .group_by(func.lower(CoworkUsage.user_principal_name))
        .subquery()
    )
    events = (
        select(
            func.lower(CoworkEvent.user_principal_name).label("upn"),
            func.count().label("cowork_events"),
            func.max(CoworkEvent.created_at).label("last_event_at"),
        )
        .where(CoworkEvent.user_principal_name.isnot(None))
        .group_by(func.lower(CoworkEvent.user_principal_name))
        .subquery()
    )
    events_by_oid = (
        select(
            CoworkEvent.user_id.label("user_id"),
            # Distinct labels from the by-UPN subquery above: both are selected
            # into the same row, and same-named columns would collide into
            # SQLAlchemy's positional "_1" suffixes, which is not something to
            # read values back out of by guessing.
            func.count().label("oid_events"),
            func.max(CoworkEvent.created_at).label("last_oid_event_at"),
        )
        .where(CoworkEvent.user_id.isnot(None))
        .group_by(CoworkEvent.user_id)
        .subquery()
    )

    stmt = (
        select(usage, events, events_by_oid, DirectoryUser)
        .select_from(DirectoryUser)
        .join(usage, usage.c.upn == func.lower(DirectoryUser.upn), isouter=True)
        .join(events, events.c.upn == func.lower(DirectoryUser.upn), isouter=True)
        .join(
            events_by_oid,
            events_by_oid.c.user_id == DirectoryUser.user_id,
            isouter=True,
        )
        .where(
            DirectoryUser.has_copilot_license.is_(True),
            or_(
                usage.c.upn.isnot(None),
                events.c.upn.isnot(None),
                events_by_oid.c.user_id.isnot(None),
            ),
        )
        .order_by(DirectoryUser.display_name)
    )
    rows = (await session.execute(stmt)).all()

    out: list[DirectoryUserOut] = []
    for r in rows:
        u = r.DirectoryUser
        # A person's events may be matched by object ID, by UPN, or both. Both
        # subqueries count the same rows when both match, so take the larger
        # rather than the sum, which would double every such person's sessions.
        by_upn = int(r.cowork_events or 0)
        by_oid = int(r.oid_events or 0)
        last_seen = max(
            (
                d
                for d in (r.last_activity_date, r.last_event_at, r.last_oid_event_at)
                if d is not None
            ),
            default=None,
        )
        out.append(
            DirectoryUserOut(
                user_principal_name=u.upn,
                display_name=u.display_name,
                job_title=u.job_title,
                department=u.department,
                company_name=u.company_name,
                office_location=u.office_location,
                city=u.city,
                country=u.country,
                manager_name=u.manager_name,
                user_type=u.user_type,
                account_enabled=u.account_enabled,
                has_copilot_license=u.has_copilot_license,
                cowork_events=max(by_upn, by_oid),
                total_tasks=int(r.total_tasks or 0),
                last_activity_date=last_seen,
            )
        )
    return out


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


@common_router.get("/about")
async def get_about() -> dict:
    """Version and build metadata for the About page."""
    from shared.version import APP_VERSION, BUILD_DATE, BUILD_TIME

    return {
        "version": APP_VERSION,
        "build_date": BUILD_DATE,
        "build_time": BUILD_TIME,
    }


@common_router.get("/freshness")
async def get_freshness(session: AsyncSession = Depends(get_session)) -> dict:
    """Data-freshness summary for the About page.

    Reports row counts and the earliest/latest dates across the two fact
    streams (audit events and Cowork usage), plus the last collector run.
    """
    from shared.models import CoworkEvent, CoworkUsage, DailyCost, DirectoryUser, JobRun

    cowork_events = await session.scalar(select(func.count()).select_from(CoworkEvent)) or 0
    usage_rows = await session.scalar(select(func.count()).select_from(CoworkUsage)) or 0
    cost_rows = await session.scalar(select(func.count()).select_from(DailyCost)) or 0
    directory_users = await session.scalar(select(func.count()).select_from(DirectoryUser)) or 0

    earliest_event = await session.scalar(select(func.min(CoworkEvent.created_at)))
    latest_event = await session.scalar(select(func.max(CoworkEvent.created_at)))
    earliest_cost = await session.scalar(select(func.min(DailyCost.cost_date)))
    latest_cost = await session.scalar(select(func.max(DailyCost.cost_date)))

    last = await session.scalar(select(JobRun).order_by(JobRun.started_at.desc()).limit(1))

    def _iso(value) -> str | None:
        return value.isoformat() if value else None

    return {
        "cowork_events": int(cowork_events),
        "cowork_usage_rows": int(usage_rows),
        "daily_cost_rows": int(cost_rows),
        "directory_users": int(directory_users),
        "earliest_event": _iso(earliest_event),
        "latest_event": _iso(latest_event),
        "earliest_cost": _iso(earliest_cost),
        "latest_cost": _iso(latest_cost),
        "last_run": (
            {
                "status": last.status,
                "started_at": _iso(last.started_at),
                "finished_at": _iso(last.finished_at),
            }
            if last
            else None
        ),
    }

# --------------------------------------------------------------------------- #
# Personal view
#
# Every route here scopes to the signed-in person using the identity carried in
# their token. There is deliberately no "which user?" parameter: if the caller
# could name the user, any viewer could read anyone's activity by editing a URL.
#
# Cowork facts are keyed two different ways — audit events carry the Entra
# object ID, while the admin-centre usage and credit exports only carry a UPN —
# so both claims are used, and the UPN is recovered from dim_user when the token
# does not carry one.
# --------------------------------------------------------------------------- #
async def _me_identity(
    user: CurrentUser, session: AsyncSession
) -> tuple[str | None, str | None]:
    """Resolve the signed-in person to (object ID, UPN), or 404.

    Falls back to the demo persona for an account with no Entra identity, so
    the personal pages work on demo data without Entra configured. The persona
    only exists while demo data is loaded, and a real ingest deletes it.
    """
    oid = await personal_view_user_id(user, session)
    if oid is None and not user.upn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There is no personal view for this account. Sign in with your "
                "work account to see your own activity."
            ),
        )
    upn = user.upn
    if oid and not upn:
        directory = await session.get(DirectoryUser, oid)
        upn = directory.upn if directory else None
    return oid, upn


def _my_usage_cond(upn: str | None):
    """Match the usage snapshot rows belonging to this person.

    UPN casing varies between the directory and the admin-centre exports, so the
    compare is case-insensitive. Without a UPN nothing can match — and that must
    mean "no rows", never "all rows".
    """
    if not upn:
        return False
    return func.lower(CoworkUsage.user_principal_name) == upn.lower()


def _my_event_cond(oid: str | None, upn: str | None):
    """Match the audit events belonging to this person (object ID or UPN)."""
    parts = []
    if oid:
        parts.append(CoworkEvent.user_id == oid)
    if upn:
        parts.append(func.lower(CoworkEvent.user_principal_name) == upn.lower())
    if not parts:
        return False
    return or_(*parts)


def _my_credit_cond(oid: str | None, upn: str | None):
    """Match the per-user credit rows belonging to this person.

    The admin-centre export identifies the user in ``scope_id`` (object ID or
    UPN, depending on the export) and sometimes only in ``scope_name``.
    """
    parts = []
    if oid:
        parts.append(func.lower(CreditConsumption.scope_id) == oid.lower())
    if upn:
        parts.append(func.lower(CreditConsumption.scope_id) == upn.lower())
        parts.append(func.lower(CreditConsumption.scope_name) == upn.lower())
    if not parts:
        return False
    return or_(*parts)


async def _my_latest_period(
    session: AsyncSession, refresh: date, upn: str | None, days: int
) -> int | None:
    """Pick the report period nearest the requested window for this person."""
    periods = (
        await session.execute(
            select(CoworkUsage.report_period)
            .where(
                CoworkUsage.report_refresh_date == refresh,
                _my_usage_cond(upn),
            )
            .distinct()
        )
    ).scalars().all()
    periods = [p for p in periods if p is not None]
    if not periods:
        return None
    return min(periods, key=lambda p: abs(p - days))


@me_router.get("/summary", response_model=MySummaryOut)
async def my_summary(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MySummaryOut:
    """This person's own Cowork activity: tasks, sessions and credits."""
    oid, upn = await _me_identity(user, session)

    display_name: str | None = None
    if oid:
        directory = await session.get(DirectoryUser, oid)
        display_name = directory.display_name if directory else None

    row = None
    period: int | None = None
    latest_refresh = await session.scalar(
        select(func.max(CoworkUsage.report_refresh_date))
    )
    if latest_refresh is not None:
        period = await _my_latest_period(session, latest_refresh, upn, days)
        row = await session.scalar(
            select(CoworkUsage).where(
                CoworkUsage.report_refresh_date == latest_refresh,
                CoworkUsage.report_period == period,
                _my_usage_cond(upn),
            )
        )

    events = await session.scalar(
        select(func.count()).select_from(CoworkEvent).where(_my_event_cond(oid, upn))
    ) or 0

    credits = 0
    latest_as_of = await session.scalar(select(func.max(CreditConsumption.as_of_date)))
    if latest_as_of is not None:
        credits = await session.scalar(
            select(func.coalesce(func.sum(CreditConsumption.credits_consumed), 0)).where(
                CreditConsumption.as_of_date == latest_as_of,
                CreditConsumption.scope_type == "user",
                _my_credit_cond(oid, upn),
            )
        ) or 0

    return MySummaryOut(
        user_principal_name=upn,
        display_name=display_name or (row.display_name if row else None),
        report_period=period,
        total_tasks=row.total_tasks if row else 0,
        scheduled_tasks=row.scheduled_tasks if row else 0,
        user_initiated_tasks=row.user_initiated_tasks if row else 0,
        active_days=row.active_days if row else 0,
        last_activity_date=row.last_activity_date if row else None,
        cowork_events=int(events),
        credits_consumed=float(credits),
        has_data=bool(row) or bool(events) or bool(credits),
    )


@me_router.get("/events", response_model=list[MyEventOut])
async def my_events(
    limit: int = Query(25, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MyEventOut]:
    """This person's most recent Cowork sessions (Purview audit events)."""
    oid, upn = await _me_identity(user, session)
    rows = (
        await session.execute(
            select(CoworkEvent)
            .where(_my_event_cond(oid, upn))
            .order_by(CoworkEvent.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        MyEventOut(
            event_id=e.event_id,
            created_at=e.created_at,
            operation=e.operation,
            app_host=e.app_host,
            agent_name=e.agent_name,
            thread_id=e.thread_id,
            tools=len(e.tools or []),
            accessed_resources=len(e.accessed_resources or []),
        )
        for e in rows
    ]


@me_router.get("/usage-trend", response_model=list[MyUsageTrendOut])
async def my_usage_trend(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MyUsageTrendOut]:
    """This person's tasks by report period for the latest snapshot."""
    _oid, upn = await _me_identity(user, session)
    latest_refresh = await session.scalar(
        select(func.max(CoworkUsage.report_refresh_date))
    )
    if latest_refresh is None:
        return []
    rows = (
        await session.execute(
            select(CoworkUsage)
            .where(
                CoworkUsage.report_refresh_date == latest_refresh,
                CoworkUsage.report_period.isnot(None),
                _my_usage_cond(upn),
            )
            .order_by(CoworkUsage.report_period)
        )
    ).scalars().all()
    return [
        MyUsageTrendOut(
            period_days=r.report_period,
            total_tasks=r.total_tasks,
            scheduled_tasks=r.scheduled_tasks,
            user_initiated_tasks=r.user_initiated_tasks,
            active_days=r.active_days,
        )
        for r in rows
    ]


@me_router.get("/comparison", response_model=MyComparisonOut)
async def my_comparison(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MyComparisonOut:
    """This person's task count against the organisation median.

    Only the aggregate is returned — never another individual's figures — so
    this stays safe to show to someone without organisation-wide access.
    """
    _oid, upn = await _me_identity(user, session)

    latest_refresh = await session.scalar(
        select(func.max(CoworkUsage.report_refresh_date))
    )
    if latest_refresh is None:
        return MyComparisonOut(
            my_tasks=0, org_median_tasks=0, people_counted=0, above_median=True
        )

    period = await _my_latest_period(session, latest_refresh, upn, days)
    if period is None:
        period = await _closest_period(session, latest_refresh, days)

    my_tasks = await session.scalar(
        select(func.coalesce(func.sum(CoworkUsage.total_tasks), 0)).where(
            CoworkUsage.report_refresh_date == latest_refresh,
            CoworkUsage.report_period == period,
            _my_usage_cond(upn),
        )
    ) or 0

    counts = sorted(
        int(c or 0)
        for c in (
            await session.execute(
                select(CoworkUsage.total_tasks).where(
                    CoworkUsage.report_refresh_date == latest_refresh,
                    CoworkUsage.report_period == period,
                    CoworkUsage.total_tasks > 0,
                )
            )
        ).scalars().all()
    )
    median = 0
    if counts:
        mid = len(counts) // 2
        median = (
            counts[mid] if len(counts) % 2 else (counts[mid - 1] + counts[mid]) // 2
        )

    my_tasks = int(my_tasks)
    return MyComparisonOut(
        my_tasks=my_tasks,
        org_median_tasks=median,
        people_counted=len(counts),
        above_median=my_tasks >= median,
    )


# --------------------------------------------------------------------------- #
# The personal page, rebuilt around aggregates
#
# Everything below reads fact_cowork_event.created_at, which is the only true
# event timestamp this app holds and is indexed. fact_cowork_usage cannot back
# any of it: it is a snapshot per rolling report window, not a daily series, so
# "tasks in the last 30 days" is a number it simply does not contain.
# --------------------------------------------------------------------------- #
class json_array_len(GenericFunction):
    """Length of a JSON array column, spelled for whichever database is under us.

    This exists because the two dialects genuinely disagree. SQLite has
    ``json_array_length``; Postgres has that name only for its ``json`` type
    and calls the ``jsonb`` one ``jsonb_array_length``. These columns are JSONB
    on Postgres, so the SQLite spelling fails there with

        (psycopg.errors.UndefinedFunction)
        function json_array_length(jsonb) does not exist

    and the test suite cannot see it, because tests/conftest.py forces SQLite.
    That is exactly how it shipped once: the personal page and the briefing both
    returned 500 against a real Postgres while 128 tests passed. There is now a
    test asserting the compiled SQL per dialect, which does catch it.

    Doing the counting in SQL rather than in Python is deliberate: the
    organisation-wide comparison would otherwise fetch a month of the whole
    tenant's events just to measure list lengths.
    """

    type = Integer()
    inherit_cache = True


@compiles(json_array_len)
def _json_array_len_default(element, compiler, **kw):
    return "json_array_length(%s)" % compiler.process(element.clauses, **kw)


@compiles(json_array_len, "postgresql")
def _json_array_len_postgresql(element, compiler, **kw):
    return "jsonb_array_length(%s)" % compiler.process(element.clauses, **kw)


def _json_len(column):
    """0 for NULL, else the array length. NULL columns are the common case."""
    return func.coalesce(
        case((column.is_(None), literal(0)), else_=json_array_len(column)), 0
    )


def _event_window(days: int):
    """Events within the window, as a filter clause."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return CoworkEvent.created_at >= since


@me_router.get("/activity", response_model=MyActivityOut)
async def my_activity(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MyActivityOut:
    """Headline figures for the personal page: sessions, tools, files, days."""
    oid, upn = await _me_identity(user, session)

    display_name: str | None = None
    if oid:
        directory = await session.get(DirectoryUser, oid)
        display_name = directory.display_name if directory else None

    row = (
        await session.execute(
            select(
                func.count().label("sessions"),
                func.coalesce(func.sum(_json_len(CoworkEvent.tools)), 0).label("tools"),
                func.coalesce(
                    func.sum(_json_len(CoworkEvent.accessed_resources)), 0
                ).label("files"),
                func.count(func.distinct(func.date(CoworkEvent.created_at))).label(
                    "active_days"
                ),
                func.max(CoworkEvent.created_at).label("last_seen"),
            ).where(_my_event_cond(oid, upn), _event_window(days))
        )
    ).one()

    return MyActivityOut(
        display_name=display_name,
        user_principal_name=upn,
        days=days,
        sessions=int(row.sessions or 0),
        tools=int(row.tools or 0),
        files=int(row.files or 0),
        active_days=int(row.active_days or 0),
        last_activity_date=row.last_seen,
        has_data=bool(row.sessions),
    )


@me_router.get("/daily", response_model=list[MyDayOut])
async def my_daily(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MyDayOut]:
    """Sessions per calendar day, with every day in the window present.

    Days with no activity are returned as zeroes rather than omitted. A bar
    chart built from only the days that happened silently rescales its x axis
    and makes a fortnight of nothing look like continuous use.
    """
    oid, upn = await _me_identity(user, session)

    day = func.date(CoworkEvent.created_at)
    rows = (
        await session.execute(
            select(
                day.label("day"),
                func.count().label("sessions"),
                func.coalesce(func.sum(_json_len(CoworkEvent.tools)), 0).label("tools"),
                func.coalesce(
                    func.sum(_json_len(CoworkEvent.accessed_resources)), 0
                ).label("files"),
            )
            .where(_my_event_cond(oid, upn), _event_window(days))
            .group_by(day)
        )
    ).all()

    def _as_date(value) -> date:
        # func.date() gives a date on Postgres and an ISO string on SQLite.
        return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])

    found = {_as_date(r.day): r for r in rows}
    today = date.today()
    out: list[MyDayOut] = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        r = found.get(d)
        out.append(
            MyDayOut(
                day=d,
                sessions=int(r.sessions) if r else 0,
                tools=int(r.tools or 0) if r else 0,
                files=int(r.files or 0) if r else 0,
            )
        )
    return out


@me_router.get("/top-agents", response_model=list[MyTopItemOut])
async def my_top_agents(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(5, ge=1, le=20),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MyTopItemOut]:
    """This person's most-used agents, by session count."""
    oid, upn = await _me_identity(user, session)
    name = func.coalesce(CoworkEvent.agent_name, CoworkEvent.app_host, "Cowork")
    rows = (
        await session.execute(
            select(name.label("name"), func.count().label("value"))
            .where(_my_event_cond(oid, upn), _event_window(days))
            .group_by(name)
            .order_by(func.count().desc())
            .limit(limit)
        )
    ).all()
    return [MyTopItemOut(name=r.name, value=int(r.value)) for r in rows]


@me_router.get("/top-tools", response_model=list[MyTopItemOut])
async def my_top_tools(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(5, ge=1, le=20),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MyTopItemOut]:
    """This person's most-used tools, by call count.

    The tool names live in a JSON array per event, and the two dialects unnest
    JSON differently enough that it is not worth a portable spelling for one
    person's month of events. The rows are already scoped to one user and one
    window, so they are counted here instead.
    """
    oid, upn = await _me_identity(user, session)
    rows = (
        await session.execute(
            select(CoworkEvent.tools).where(
                _my_event_cond(oid, upn),
                _event_window(days),
                CoworkEvent.tools.isnot(None),
            )
        )
    ).scalars().all()

    counts: dict[str, int] = {}
    for tools in rows:
        for tool in tools or []:
            # Entries are usually plain strings; a dict with a name is tolerated
            # rather than rendered as its repr.
            label = tool.get("name") if isinstance(tool, dict) else tool
            if not label:
                continue
            counts[str(label)] = counts.get(str(label), 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [MyTopItemOut(name=n, value=v) for n, v in ranked]


# A team series is only drawn when the grouping holds at least this many people
# besides the viewer.
#
# This is a disclosure rule, not a presentation preference. "Aggregates only"
# stops being true at small n: with two people in a team, the team figure and
# the viewer's own figure together give the other person's exact number, and
# anyone can do that arithmetic in their head. At three or four it is close
# enough to matter. The floor applies to whichever grouping is in use —
# falling back from a department of one to a manager group of two fixes
# nothing. See docs/specs/comparisons-and-timelines.md.
#
# The consequence, stated plainly: in a small tenant, or one that populates
# departments sparsely, most people see two series rather than three. That is
# the correct outcome. The alternative is a report that quietly discloses
# colleagues' usage.
MIN_TEAM_PEERS = 5


def _median(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


@me_router.get("/standing", response_model=MyStandingOut)
async def my_standing(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MyStandingOut:
    """How this person compares with their team and the wider organisation.

    Only medians and a percentile leave this endpoint. No other individual's
    figures are returned in any form, which is what keeps it safe to show to
    someone who has no organisation-wide access at all — the personal page is
    reachable by every signed-in user by design.

    "Team" is the department, falling back to the people sharing this person's
    manager when the department is unknown or too small. It is omitted rather
    than shown as zero in two cases, and the response says which: the grouping
    holds fewer than MIN_TEAM_PEERS people besides the viewer, or no grouping
    is known at all. An empty bar reads as "you are miles ahead of your team"
    when it actually means one of those two things, and they are different
    facts about the tenant — one is fixed by populating departments, the other
    cannot be fixed and should not be.
    """
    oid, upn = await _me_identity(user, session)

    # Per-person totals across the whole window, in one pass. Events are keyed
    # by object ID where present and by UPN otherwise, so the grouping key has
    # to tolerate both — dim_user is joined on either.
    person = func.coalesce(
        DirectoryUser.user_id, func.lower(CoworkEvent.user_principal_name)
    )
    totals = (
        await session.execute(
            select(
                person.label("person"),
                DirectoryUser.department.label("department"),
                DirectoryUser.manager_name.label("manager_name"),
                func.count().label("sessions"),
                func.coalesce(func.sum(_json_len(CoworkEvent.tools)), 0).label("tools"),
                func.coalesce(
                    func.sum(_json_len(CoworkEvent.accessed_resources)), 0
                ).label("files"),
            )
            .select_from(CoworkEvent)
            .join(
                DirectoryUser,
                or_(
                    DirectoryUser.user_id == CoworkEvent.user_id,
                    func.lower(DirectoryUser.upn)
                    == func.lower(CoworkEvent.user_principal_name),
                ),
                isouter=True,
            )
            .where(_event_window(days))
            .group_by(person, DirectoryUser.department, DirectoryUser.manager_name)
        )
    ).all()

    me_key = (oid or (upn.lower() if upn else None)) or None
    mine = next((r for r in totals if r.person == me_key), None)

    # Who counts as "my team", and whether there are enough of them to draw.
    # The department is tried first; a department too small to pass the floor
    # falls back to the people sharing a manager, which is a different grouping
    # and can be larger. If neither clears it, no team series is drawn.
    team_label: str | None = None
    peers: list = []
    if mine is not None:
        dept = (mine.department or "").strip()
        if dept:
            peers = [
                r for r in totals if r.department == dept and r.person != me_key
            ]
            team_label = dept
        if len(peers) < MIN_TEAM_PEERS:
            mgr = (mine.manager_name or "").strip()
            if mgr:
                mgr_peers = [
                    r for r in totals if r.manager_name == mgr and r.person != me_key
                ]
                # Only take the fallback if it is actually an improvement.
                # Swapping a department of four for a manager group of two
                # trades one withheld series for another and loses the label
                # that was at least accurate.
                if len(mgr_peers) > len(peers):
                    peers = mgr_peers
                    team_label = f"{mgr}'s team"

    show_team = len(peers) >= MIN_TEAM_PEERS
    if show_team:
        team_state = "shown"
    elif peers:
        team_state = "too_small"
    else:
        team_state = "unknown"
    if not show_team:
        team_label = None

    def _stat(label: str, attr: str) -> PeerStatOut:
        org_values = [int(getattr(r, attr) or 0) for r in totals]
        peer_values = [int(getattr(r, attr) or 0) for r in peers]
        return PeerStatOut(
            label=label,
            mine=int(getattr(mine, attr) or 0) if mine is not None else 0,
            # Withheld means withheld: the figure is not sent and then hidden
            # by the page, because a number that reaches the browser has been
            # disclosed whatever the page does with it.
            team_median=_median(peer_values) if show_team else 0,
            org_median=_median(org_values),
            team_people=len(peers) if show_team else 0,
            org_people=len(org_values),
        )

    # Percentile on sessions: the share of counted people this person did more
    # than. Ties count as "not more than", so the busiest person is 100 and
    # someone level with everybody is 0 rather than an arbitrary middle.
    #
    # Measured across every counted person — the organisation — never across
    # the team. In a team of six, a team-relative percentile moves in steps of
    # 17 points and says more about the size of the team than the person.
    sessions = [int(r.sessions or 0) for r in totals]
    my_sessions = int(mine.sessions or 0) if mine is not None else 0
    percentile = (
        round(100 * sum(1 for v in sessions if v < my_sessions) / len(sessions))
        if sessions
        else 0
    )

    # The window every series was computed over, so the panel can name it. All
    # three come from the one filtered pass above, so they cannot disagree
    # about which period they describe — but the reader has no way of knowing
    # that unless the dates are on screen.
    period_to = date.today()
    period_from = period_to - timedelta(days=days - 1)

    return MyStandingOut(
        team_label=team_label,
        team_state=team_state,
        team_peers=len(peers),
        min_team_peers=MIN_TEAM_PEERS,
        period_days=days,
        period_from=period_from,
        period_to=period_to,
        org_percentile=percentile,
        org_people=len(totals),
        stats=[
            _stat("Sessions", "sessions"),
            _stat("Tools used", "tools"),
            _stat("Files touched", "files"),
        ],
    )


# --------------------------------------------------------------------------- #
# Executive briefing
#
# Deterministic by design. Every figure below is SQL, and the page assembles
# its prose from them against fixed thresholds. Nothing is written by a model:
# this is the screen most likely to be put in front of a customer or a finance
# team, and a fabricated number there costs more than the feature is worth.
# --------------------------------------------------------------------------- #
def _pct_change(current: float, previous: float) -> float | None:
    """Percentage change, or None when there is no honest one to report.

    A previous period of zero has no percentage — "up from nothing" is not
    +100%, and it is not infinity either. Returning None lets the page say
    "new this period" instead of printing a number that means nothing.
    """
    if not previous:
        return None
    return round(((current - previous) / previous) * 100, 1)


@router.get("/briefing", response_model=BriefingOut)
async def briefing(
    days: int = Query(30, ge=7, le=180),
    session: AsyncSession = Depends(get_session),
) -> BriefingOut:
    """This period against the one before it, plus who and what is leading."""
    today = date.today()
    cur_start = today - timedelta(days=days)
    prev_start = today - timedelta(days=2 * days)
    cur_start_dt = datetime.combine(cur_start, datetime.min.time(), timezone.utc)
    prev_start_dt = datetime.combine(prev_start, datetime.min.time(), timezone.utc)

    async def _events(lo: datetime, hi: datetime | None) -> tuple[int, int, int]:
        conds = [CoworkEvent.created_at >= lo]
        if hi is not None:
            conds.append(CoworkEvent.created_at < hi)
        row = (
            await session.execute(
                select(
                    func.count().label("sessions"),
                    func.coalesce(func.sum(_json_len(CoworkEvent.tools)), 0).label(
                        "tools"
                    ),
                    func.coalesce(
                        func.sum(_json_len(CoworkEvent.accessed_resources)), 0
                    ).label("files"),
                ).where(*conds)
            )
        ).one()
        return int(row.sessions or 0), int(row.tools or 0), int(row.files or 0)

    async def _cost(lo: date, hi: date | None) -> float:
        conds = [DailyCost.cost_date >= lo]
        if hi is not None:
            conds.append(DailyCost.cost_date < hi)
        return float(
            await session.scalar(
                select(func.coalesce(func.sum(DailyCost.cost), 0)).where(*conds)
            )
            or 0
        )

    cur_sessions, cur_tools, cur_files = await _events(cur_start_dt, None)
    prev_sessions, prev_tools, prev_files = await _events(prev_start_dt, cur_start_dt)
    cur_cost = await _cost(cur_start, None)
    prev_cost = await _cost(prev_start, cur_start)

    currency = await session.scalar(
        select(DailyCost.currency).where(DailyCost.currency.isnot(None)).limit(1)
    )

    # Licensed-user adoption: how many of the people we are paying for did
    # anything at all. This is the ratio a renewal conversation turns on.
    licensed = int(
        await session.scalar(
            select(func.count())
            .select_from(DirectoryUser)
            .where(DirectoryUser.has_copilot_license.is_(True))
        )
        or 0
    )
    active_licensed = int(
        await session.scalar(
            select(func.count(func.distinct(DirectoryUser.user_id)))
            .select_from(DirectoryUser)
            .join(
                CoworkEvent,
                or_(
                    CoworkEvent.user_id == DirectoryUser.user_id,
                    func.lower(CoworkEvent.user_principal_name)
                    == func.lower(DirectoryUser.upn),
                ),
            )
            .where(
                DirectoryUser.has_copilot_license.is_(True),
                CoworkEvent.created_at >= cur_start_dt,
            )
        )
        or 0
    )

    async def _top(column, lo: datetime, hi: datetime | None, limit: int = 5):
        conds = [CoworkEvent.created_at >= lo, column.isnot(None)]
        if hi is not None:
            conds.append(CoworkEvent.created_at < hi)
        rows = (
            await session.execute(
                select(column.label("name"), func.count().label("value"))
                .where(*conds)
                .group_by(column)
                .order_by(func.count().desc())
                .limit(limit)
            )
        ).all()
        return {r.name: int(r.value) for r in rows}

    cur_agents = await _top(CoworkEvent.agent_name, cur_start_dt, None)
    prev_agents = await _top(CoworkEvent.agent_name, prev_start_dt, cur_start_dt, 50)

    rg_rows = (
        await session.execute(
            select(
                DailyCost.resource_group.label("name"),
                func.coalesce(func.sum(DailyCost.cost), 0).label("value"),
            )
            .where(DailyCost.cost_date >= cur_start, DailyCost.resource_group.isnot(None))
            .group_by(DailyCost.resource_group)
            .order_by(func.sum(DailyCost.cost).desc())
            .limit(5)
        )
    ).all()
    prev_rg = dict(
        (
            await session.execute(
                select(
                    DailyCost.resource_group,
                    func.coalesce(func.sum(DailyCost.cost), 0),
                )
                .where(
                    DailyCost.cost_date >= prev_start,
                    DailyCost.cost_date < cur_start,
                    DailyCost.resource_group.isnot(None),
                )
                .group_by(DailyCost.resource_group)
            )
        ).all()
    )

    deltas = [
        BriefingDeltaOut(
            label=label,
            current=cur,
            previous=prev,
            change_pct=_pct_change(cur, prev),
        )
        for label, cur, prev in (
            ("Sessions", cur_sessions, prev_sessions),
            ("Tools used", cur_tools, prev_tools),
            ("Files touched", cur_files, prev_files),
            ("Azure cost", round(cur_cost, 2), round(prev_cost, 2)),
        )
    ]

    return BriefingOut(
        window_days=days,
        period_start=cur_start,
        previous_start=prev_start,
        has_data=bool(cur_sessions or prev_sessions or cur_cost or prev_cost),
        currency=currency,
        deltas=deltas,
        licensed_users=licensed,
        active_licensed_users=active_licensed,
        idle_licensed_users=max(licensed - active_licensed, 0),
        top_agents=[
            BriefingItemOut(
                name=name, value=value, previous=prev_agents.get(name, 0)
            )
            for name, value in cur_agents.items()
        ],
        top_resource_groups=[
            BriefingItemOut(
                name=r.name,
                value=round(float(r.value or 0), 2),
                previous=round(float(prev_rg.get(r.name, 0) or 0), 2),
            )
            for r in rg_rows
        ],
    )
