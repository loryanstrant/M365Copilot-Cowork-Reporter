"""Admin routes (admin role required).

Configure credentials (Graph + ARM app registration, secret encrypted), test the
connection, trigger an ingest, edit the billing-policy chargeback mapping, and
read run status. All routes are gated by :func:`api.auth.require_admin`.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentUser, require_admin
from api.schemas import (
    AppConfigIn,
    AppConfigOut,
    BillingPolicyIn,
    BillingPolicyOut,
    IngestRunOut,
    JobRunOut,
    StatusOut,
    TestConnectionOut,
)
from shared.crypto import encrypt
from shared.db import SessionLocal, get_session
from shared.models import (
    AppConfig,
    BillingPolicy,
    CoworkEvent,
    CoworkUsage,
    CreditConsumption,
    DailyCost,
    DirectoryUser,
    JobRun,
)
from worker.ingest import run_ingest, test_connection

logger = logging.getLogger("api.admin")

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_ingest_lock = asyncio.Lock()


def _to_out(cfg: AppConfig | None) -> AppConfigOut:
    if cfg is None:
        return AppConfigOut()
    return AppConfigOut(
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        has_client_secret=bool(cfg.client_secret_encrypted),
        azure_subscription_ids=list(cfg.azure_subscription_ids or []),
        cost_rolling_window_days=cfg.cost_rolling_window_days or 10,
        audit_backfill_days=cfg.audit_backfill_days or 30,
        report_access_group_id=cfg.report_access_group_id,
        schedule_interval_hours=cfg.schedule_interval_hours or 8,
        configured=bool(
            cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted
        ),
        updated_at=cfg.updated_at,
        updated_by=cfg.updated_by,
    )


async def _get_config(session: AsyncSession) -> AppConfig | None:
    return await session.get(AppConfig, 1)


@router.get("/config", response_model=AppConfigOut)
async def get_config(session: AsyncSession = Depends(get_session)) -> AppConfigOut:
    return _to_out(await _get_config(session))


@router.put("/config", response_model=AppConfigOut)
async def put_config(
    body: AppConfigIn,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AppConfigOut:
    cfg = await _get_config(session)
    if cfg is None:
        cfg = AppConfig(id=1, azure_subscription_ids=[])
        session.add(cfg)

    if body.tenant_id is not None:
        cfg.tenant_id = body.tenant_id.strip() or None
    if body.client_id is not None:
        cfg.client_id = body.client_id.strip() or None
    if body.client_secret:
        cfg.client_secret_encrypted = encrypt(body.client_secret)
    if body.azure_subscription_ids is not None:
        cfg.azure_subscription_ids = [
            s.strip() for s in body.azure_subscription_ids if s.strip()
        ]
    if body.cost_rolling_window_days is not None:
        cfg.cost_rolling_window_days = max(1, min(body.cost_rolling_window_days, 90))
    if body.audit_backfill_days is not None:
        cfg.audit_backfill_days = max(1, min(body.audit_backfill_days, 180))
    if body.report_access_group_id is not None:
        cfg.report_access_group_id = body.report_access_group_id.strip() or None
    if body.schedule_interval_hours is not None:
        cfg.schedule_interval_hours = max(1, min(body.schedule_interval_hours, 24))
    cfg.updated_by = user.username

    await session.commit()
    await session.refresh(cfg)
    return _to_out(cfg)


@router.post("/test-connection", response_model=TestConnectionOut)
async def test_conn(session: AsyncSession = Depends(get_session)) -> TestConnectionOut:
    cfg = await _get_config(session)
    if cfg is None:
        return TestConnectionOut(ok=False, detail="Not configured yet.")
    return TestConnectionOut(**await test_connection(cfg))


async def _run_manual_ingest() -> None:
    async with _ingest_lock:
        try:
            await run_ingest(SessionLocal, job_name="manual")
        except Exception:  # pragma: no cover - logged for observability
            logger.exception("Manual ingest failed")


@router.post("/ingest/run", response_model=IngestRunOut)
async def ingest_run(background: BackgroundTasks) -> IngestRunOut:
    if _ingest_lock.locked():
        return IngestRunOut(
            status="already_running", detail="An ingest is already in progress."
        )
    background.add_task(_run_manual_ingest)
    return IngestRunOut(status="started", detail="Ingest started in the background.")


@router.post("/seed-demo", response_model=IngestRunOut)
async def seed_demo(reset: bool = True) -> IngestRunOut:
    """Seed synthetic Cowork data so the dashboards render without live sources."""
    from scripts.seed_demo import seed

    stats = await seed(reset)
    return IngestRunOut(
        status="seeded",
        detail=(
            f"Seeded {stats['cost_rows']} cost rows, {stats['events']} events, "
            f"{stats['usage_rows']} usage rows, {stats['credit_rows']} credit rows."
        ),
    )


# --- billing policy (chargeback mapping) --------------------------------
@router.get("/billing-policies", response_model=list[BillingPolicyOut])
async def list_billing_policies(
    session: AsyncSession = Depends(get_session),
) -> list[BillingPolicyOut]:
    rows = (
        await session.execute(select(BillingPolicy).order_by(BillingPolicy.resource_group))
    ).scalars().all()
    return [BillingPolicyOut.model_validate(r, from_attributes=True) for r in rows]


@router.put("/billing-policies", response_model=BillingPolicyOut)
async def upsert_billing_policy(
    body: BillingPolicyIn,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BillingPolicyOut:
    rg = body.resource_group.strip().lower()
    row = await session.get(BillingPolicy, rg)
    if row is None:
        row = BillingPolicy(resource_group=rg)
        session.add(row)
    row.billing_policy_name = body.billing_policy_name
    row.cost_centre = body.cost_centre
    row.business_owner = body.business_owner
    row.project = body.project
    row.notes = body.notes
    row.updated_by = user.username
    await session.commit()
    await session.refresh(row)
    return BillingPolicyOut.model_validate(row, from_attributes=True)


@router.delete("/billing-policies/{resource_group}", response_model=IngestRunOut)
async def delete_billing_policy(
    resource_group: str, session: AsyncSession = Depends(get_session)
) -> IngestRunOut:
    row = await session.get(BillingPolicy, resource_group.strip().lower())
    if row:
        await session.delete(row)
        await session.commit()
    return IngestRunOut(status="deleted", detail=resource_group)


@router.get("/status", response_model=StatusOut)
async def status(session: AsyncSession = Depends(get_session)) -> StatusOut:
    cfg = await _get_config(session)
    last = await session.scalar(
        select(JobRun)
        .where(JobRun.job_name.in_(["manual", "scheduled"]))
        .order_by(JobRun.started_at.desc())
        .limit(1)
    )

    async def _count(model) -> int:
        return await session.scalar(select(func.count()).select_from(model)) or 0

    last_out = (
        JobRunOut(
            id=last.id, job_name=last.job_name, status=last.status,
            started_at=last.started_at, finished_at=last.finished_at, stats=last.stats,
        )
        if last is not None
        else None
    )
    return StatusOut(
        configured=bool(
            cfg and cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted
        ),
        last_run=last_out,
        cowork_events=await _count(CoworkEvent),
        daily_cost_rows=await _count(DailyCost),
        cowork_usage_rows=await _count(CoworkUsage),
        credit_rows=await _count(CreditConsumption),
        directory_users=await _count(DirectoryUser),
    )
