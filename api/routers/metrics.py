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

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentUser, get_current_user, require_org_view
from api.schemas import (
    CostByGroupOut,
    CostTrendOut,
    DirectoryUserOut,
    KpiOut,
    MyComparisonOut,
    MyEventOut,
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
    """Resolve the signed-in person to (object ID, UPN), or 404."""
    if not user.has_personal_view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There is no personal view for this account. Sign in with your "
                "work account to see your own activity."
            ),
        )
    oid, upn = user.oid, user.upn
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
