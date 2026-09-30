"""Ingestion engine — the supported, app-only collectors.

Three collectors, run on a fixed cadence by :mod:`worker.main`:

1. **Azure cost** — Cost Management Query API, grouped by resource group + meter,
   with a **rolling-window replace** of the trailing N days (cost data restates,
   so this is idempotent and self-healing).
2. **Purview audit** — a ``CopilotInteraction`` query job, filtered to Cowork
   rows, upserted idempotently on ``event_id``.
3. **Directory users** — Entra org context for chargeback/adoption joins.

The two admin-centre exports (Cowork usage, credit consumption) have no API and
are handled by CSV upload in :mod:`worker.csv_import`, not here.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.crypto import decrypt
from shared.models import (
    AppConfig,
    CoworkEvent,
    DailyCost,
    DirectoryUser,
    IngestState,
    JobRun,
)
from shared.demo import retire_demo_persona
from shared.upsert import bulk_upsert
from worker.graph import ApiClient, AppAuth, GraphError
from worker.licensing import copilot_granting_skus
from worker.transforms import (
    is_cowork_event,
    is_included_directory_user,
    now_utc,
    transform_cost_rows,
    transform_cowork_event,
    transform_directory_user,
)

logger = logging.getLogger("worker.ingest")

SessionFactory = Callable[[], AsyncSession]

_EVENT_UPDATE_KEYS = [
    "created_at", "user_id", "user_principal_name", "operation", "app_host",
    "app_identity", "agent_name", "thread_id", "client_ip", "tools",
    "accessed_resources", "prompt_message_count", "response_message_count",
    "raw_json",
]
_USER_UPDATE_KEYS = [
    "has_copilot_license",
    # Stamped on every sync so "when did the directory last return this person"
    # is answerable. ON CONFLICT DO UPDATE does not fire the column's onupdate,
    # so without this the timestamp records when a row was first inserted and
    # nothing else — which is how a user carrying a NULL licence was left
    # indistinguishable from one the sync had simply stopped returning.
    "updated_at",
    "upn", "email", "display_name", "given_name", "surname", "job_title",
    "company_name", "department", "office_location", "city", "state", "country",
    "usage_location", "employee_id", "employee_type", "manager_id",
    "manager_name", "account_enabled", "user_type",
    *[f"ext{i}" for i in range(1, 16)],
]


class IngestError(RuntimeError):
    """Raised when ingestion cannot run (e.g. credentials not configured)."""


async def load_app_config(session: AsyncSession) -> AppConfig | None:
    return await session.get(AppConfig, 1)


def build_client(config: AppConfig) -> ApiClient:
    if not (config.tenant_id and config.client_id and config.client_secret_encrypted):
        raise IngestError("Graph/Azure credentials are not fully configured.")
    secret = decrypt(config.client_secret_encrypted)
    auth = AppAuth(config.tenant_id, config.client_id, secret)
    return ApiClient(auth, concurrency=settings.ingest_concurrency)


# --- collectors ---------------------------------------------------------
async def collect_costs(
    session: AsyncSession, client: ApiClient, config: AppConfig, now: datetime
) -> dict[str, Any]:
    """Rolling-window replace of Azure daily cost for each subscription."""
    subs = list(config.azure_subscription_ids or [])
    if not subs:
        return {"subscriptions": 0, "rows": 0, "skipped": "no subscriptions configured"}

    window = max(1, config.cost_rolling_window_days or 10)
    start = now - timedelta(days=window)
    total_rows = 0
    for sub in subs:
        payload = await client.query_cost_by_resource_group(sub, start, now)
        rows = transform_cost_rows(sub, payload)
        # Rolling-window replace: wipe this subscription's trailing window, reinsert.
        await session.execute(
            delete(DailyCost).where(
                DailyCost.subscription_id == sub,
                DailyCost.cost_date >= start.date(),
            )
        )
        total_rows += await bulk_upsert(
            session, DailyCost, rows,
            index_elements=[
                "cost_date", "subscription_id", "resource_group",
                "meter_category", "meter_name",
            ],
            update_keys=["service_name", "cost", "currency"],
        )
    return {"subscriptions": len(subs), "rows": total_rows, "window_days": window}


async def resolve_event_identities(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Normalise audit identities against the directory, in place.

    The audit ``UserId`` is a mixture — an Entra object ID on some rows, a UPN
    on others, in the same tenant on the same day. Left as it arrives, the
    natural key of ``fact_cowork_event`` is two different keys, and an event
    stored under a UPN cannot join to ``dim_user`` at all: on the live tenant
    only 15 of 80 events joined.

    ``dim_user.user_id`` is the Entra object ID and is the key everything else
    hangs off, so that is what we normalise *to*. Each row gets:

    * ``user_id`` — the directory's object ID when the audit value matched a
      directory user by either key;
    * ``user_principal_name`` — the directory's UPN, so the UPN column holds
      sign-in names and nothing else.

    **An unmatched row is kept exactly as it arrived.** Dropping it would be
    losing a fact: the interaction happened, and a person who has since left
    the tenant, or a UPN the directory sync has not seen yet, is still usage
    that belongs on the organisation's totals. It keeps its raw identifier,
    the read paths still match it by UPN, and a later directory sync plus a
    re-run of this resolution will attach it to its person.
    """
    if not rows:
        return rows

    wanted = {str(r["user_id"]).lower() for r in rows if r.get("user_id")}
    wanted |= {
        str(r["user_principal_name"]).lower()
        for r in rows
        if r.get("user_principal_name")
    }
    if not wanted:
        return rows

    directory = (
        await session.execute(
            select(DirectoryUser.user_id, DirectoryUser.upn).where(
                or_(
                    func.lower(DirectoryUser.user_id).in_(wanted),
                    func.lower(DirectoryUser.upn).in_(wanted),
                )
            )
        )
    ).all()
    by_key: dict[str, tuple[str, str | None]] = {}
    for user_id, upn in directory:
        if user_id:
            by_key[user_id.lower()] = (user_id, upn)
        if upn:
            by_key[upn.lower()] = (user_id, upn)

    for row in rows:
        candidates = [row.get("user_id"), row.get("user_principal_name")]
        matches = [
            by_key[str(c).lower()] for c in candidates if c and str(c).lower() in by_key
        ]
        if not matches:
            continue
        # The two columns can name two different people. Purview's UserId is
        # who the interaction was recorded against, and a record's own
        # userPrincipalName can be someone else entirely — a delegated or
        # on-behalf-of action. The audit UserId wins, because it is the field
        # the audit log is keyed on, but a disagreement is worth a line in the
        # log: it is the only visible sign that we chose between two people.
        if len({m[0] for m in matches}) > 1:
            logger.warning(
                "Event %s names two directory users (%s vs %s); keying it on "
                "the audit UserId.",
                row.get("event_id"),
                matches[0][0],
                matches[1][0],
            )
        user_id, upn = matches[0]
        row["user_id"] = user_id
        if upn:
            row["user_principal_name"] = upn
    return rows


async def collect_cowork_events(
    session: AsyncSession, client: ApiClient, config: AppConfig, now: datetime
) -> dict[str, Any]:
    """Run a Purview audit query and upsert Cowork rows on ``event_id``."""
    wm = await session.scalar(
        select(IngestState.watermark).where(IngestState.key == "audit")
    )
    if wm is None:
        start = now - timedelta(days=config.audit_backfill_days or 30)
    else:
        # Small overlap so late-committed audit rows aren't missed.
        start = wm - timedelta(hours=2)

    query_id = await client.create_audit_query(start, now, display_name="cowork-ingest")
    await client.wait_for_audit_query(query_id)

    rows: list[dict[str, Any]] = []
    scanned = 0
    async for rec in client.iter_audit_records(query_id):
        scanned += 1
        if not is_cowork_event(rec):
            continue
        row = transform_cowork_event(rec)
        if row:
            rows.append(row)

    await resolve_event_identities(session, rows)
    inserted = await bulk_upsert(
        session, CoworkEvent, rows,
        index_elements=["event_id"], update_keys=_EVENT_UPDATE_KEYS,
    )
    await bulk_upsert(
        session, IngestState,
        [{"key": "audit", "watermark": now, "last_status": "ok", "last_run_at": now}],
        index_elements=["key"],
        update_keys=["watermark", "last_status", "last_run_at"],
    )
    return {"scanned": scanned, "cowork_events": inserted}


async def resolve_granting_skus(client: ApiClient) -> set[str]:
    """Which of this tenant's own SKUs grant Copilot.

    Asked once per ingest. A tenant that owns no Copilot subscription returns
    an empty set, which is a real answer — everyone is then unlicensed — and
    not an error. Cowork reads the whole directory and flags each row, so
    unlike a SKU-filtered query there is no OData filter here for an empty set
    to collapse into.
    """
    skus = await client.get_subscribed_skus()
    return copilot_granting_skus(skus)


async def collect_directory_users(
    session: AsyncSession, client: ApiClient
) -> dict[str, Any]:
    """Upsert enabled member users into ``dim_user``, flagging Copilot licences."""
    batch: list[dict[str, Any]] = []
    count = 0

    try:
        granting = await resolve_granting_skus(client)
    except Exception as exc:
        # Licence detection is an enrichment, not the point of this collector.
        # If /subscribedSkus fails, still import the directory rather than lose
        # every user — they are flagged unlicensed until the next successful run.
        logger.warning("Could not read subscribed SKUs, licences unresolved: %s", exc)
        granting = set()
    if not granting:
        logger.info("No subscription in this tenant grants Copilot.")

    async def flush() -> int:
        nonlocal batch
        if not batch:
            return 0
        n = await bulk_upsert(
            session, DirectoryUser, batch,
            index_elements=["user_id"], update_keys=_USER_UPDATE_KEYS,
        )
        batch = []
        return n

    seen_at = now_utc()
    async for user in client.iter_directory_users():
        if not is_included_directory_user(user):
            continue
        row = transform_directory_user(user, granting)
        batch.append({**row, "updated_at": seen_at})
        if len(batch) >= 500:
            count += await flush()
    count += await flush()
    return {"users": count, "copilot_licensed": len(granting)}


# --- orchestrator -------------------------------------------------------
async def run_ingest(
    session_factory: SessionFactory,
    *,
    client: ApiClient | None = None,
    config: AppConfig | None = None,
    job_name: str = "scheduled",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run all app-only collectors and record the run in ``job_runs``."""
    now = now or datetime.now(timezone.utc)
    owns_client = False

    async with session_factory() as session:
        if config is None:
            config = await load_app_config(session)
            if config is None or not config.tenant_id:
                raise IngestError("Credentials are not configured yet.")
        if client is None:
            client = build_client(config)
            owns_client = True

        job = JobRun(job_name=job_name, status="running")
        session.add(job)
        await session.flush()
        await session.commit()
        stats: dict[str, Any] = {}
        try:
            # Each collector commits independently so a slow/failing audit step
            # never blocks directory users or cost from landing.
            stats["users"] = await collect_directory_users(session, client)
            await session.commit()
            stats["cost"] = await collect_costs(session, client, config, now)
            await session.commit()
            stats["audit"] = await collect_cowork_events(session, client, config, now)
            await session.commit()
            # Real data has arrived, so a demo persona the local admin was
            # borrowing is now actively misleading — it would go on presenting
            # a fictional person's activity as their own. Retire it here rather
            # than relying on someone remembering to press Clear demo data;
            # real data landing is a better signal than a button nobody has to
            # press.
            await retire_demo_persona(session)
            job.status = "success"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            logger.info("Ingest '%s' complete: %s", job_name, stats)
            return stats
        except Exception as exc:  # noqa: BLE001 - persisted for observability
            await session.rollback()
            stats["error"] = str(exc)
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            logger.exception("Ingest '%s' failed", job_name)
            raise
        finally:
            if owns_client and client is not None:
                await client.aclose()


async def test_connection(config: AppConfig) -> dict[str, Any]:
    """Validate credentials + permissions with light calls. Never raises."""
    result: dict[str, Any] = {
        "ok": False,
        "graph_token": False,
        "arm_token": False,
        "directory_read": False,
        "audit_query": False,
        "cost_read": False,
        "directory_users": None,
        "detail": None,
    }
    try:
        client = build_client(config)
    except IngestError as exc:
        result["detail"] = str(exc)
        return result
    try:
        await client.acquire_graph_token()
        result["graph_token"] = True

        count = 0
        async for _ in client.iter_directory_users():
            count += 1
            if count >= 1:
                break
        result["directory_read"] = True
        # Full count is cheap enough for a tenant of this size but keep it light.
        result["directory_users"] = None

        now = now_utc()
        qid = await client.create_audit_query(
            now.replace(hour=0, minute=0, second=0, microsecond=0), now,
            display_name="cowork-connection-test",
        )
        result["audit_query"] = bool(qid)

        if config.azure_subscription_ids:
            await client.acquire_arm_token()
            result["arm_token"] = True
            sub = config.azure_subscription_ids[0]
            from datetime import timedelta as _td
            await client.query_cost_by_resource_group(sub, now - _td(days=2), now)
            result["cost_read"] = True
        result["ok"] = result["graph_token"] and result["directory_read"]
    except (GraphError, Exception) as exc:  # noqa: BLE001 - reported to caller
        result["detail"] = str(exc)
    finally:
        await client.aclose()
    return result


async def count_events(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(CoworkEvent))).scalar_one()
    )
