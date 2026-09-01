"""Historical Purview audit backfill.

The recurring collector (:mod:`worker.ingest`) only reaches back
``audit_backfill_days`` on its first run and then rides a watermark. This module
does a **deep** one-off backfill, chunking the range into monthly windows (a
single audit query can be large and slow over long ranges) and upserting Cowork
rows idempotently on ``event_id``. Progress is tracked in-process so the admin UI
can show a live bar, and each run is recorded in ``job_runs``.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import CoworkEvent, JobRun
from shared.upsert import bulk_upsert
from worker.ingest import IngestError, build_client, load_app_config
from worker.ingest import _EVENT_UPDATE_KEYS  # reuse the same update column set
from worker.transforms import is_cowork_event, transform_cowork_event

logger = logging.getLogger("worker.backfill")

SessionFactory = Callable[[], AsyncSession]

# Cowork reached GA in June 2026; nothing meaningful exists before it.
_COWORK_GA = datetime(2026, 6, 1, tzinfo=timezone.utc)
_CHUNK_DAYS = 30

# In-process progress for the admin UI (single-instance worker/api).
_progress: dict[str, Any] = {
    "running": False,
    "windows_total": 0,
    "windows_done": 0,
    "scanned": 0,
    "cowork_events": 0,
    "current_window": None,
    "error": None,
}
_cancel = {"flag": False}


def get_progress() -> dict[str, Any]:
    return dict(_progress)


def is_running() -> bool:
    return _progress["running"]


def request_cancel() -> None:
    _cancel["flag"] = True


def _windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=_CHUNK_DAYS), end)
        out.append((cur, nxt))
        cur = nxt
    return out


async def run_backfill(
    session_factory: SessionFactory,
    *,
    lookback_days: int | None = None,
) -> dict[str, Any]:
    """Backfill Cowork audit events over a deep historical range.

    ``lookback_days`` bounds how far back to reach; it is clamped to Cowork GA so
    we never issue pointless queries for periods before Cowork existed.
    """
    now = datetime.now(timezone.utc)
    if lookback_days:
        start = now - timedelta(days=lookback_days)
    else:
        start = _COWORK_GA
    start = max(start, _COWORK_GA)

    windows = _windows(start, now)
    _cancel["flag"] = False
    _progress.update({
        "running": True, "windows_total": len(windows), "windows_done": 0,
        "scanned": 0, "cowork_events": 0, "current_window": None, "error": None,
    })

    async with session_factory() as session:
        config = await load_app_config(session)
        if config is None or not config.tenant_id:
            _progress.update({"running": False, "error": "not configured"})
            raise IngestError("Credentials are not configured yet.")
        client = build_client(config)

        job = JobRun(job_name="backfill", status="running")
        session.add(job)
        await session.flush()

        total_events = 0
        total_scanned = 0
        try:
            for (wstart, wend) in windows:
                if _cancel["flag"]:
                    logger.info("Backfill cancelled by request.")
                    break
                _progress["current_window"] = f"{wstart.date()} → {wend.date()}"
                query_id = await client.create_audit_query(
                    wstart, wend, display_name=f"cowork-backfill-{wstart.date()}"
                )
                await client.wait_for_audit_query(query_id)

                rows: list[dict[str, Any]] = []
                async for rec in client.iter_audit_records(query_id):
                    total_scanned += 1
                    _progress["scanned"] = total_scanned
                    if is_cowork_event(rec):
                        row = transform_cowork_event(rec)
                        if row:
                            rows.append(row)
                inserted = await bulk_upsert(
                    session, CoworkEvent, rows,
                    index_elements=["event_id"], update_keys=_EVENT_UPDATE_KEYS,
                )
                await session.commit()
                total_events += inserted
                _progress["cowork_events"] = total_events
                _progress["windows_done"] += 1
                logger.info(
                    "Backfill window %s: scanned=%d cowork=%d",
                    _progress["current_window"], total_scanned, inserted,
                )

            job.status = "cancelled" if _cancel["flag"] else "success"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = {
                "windows": len(windows),
                "windows_done": _progress["windows_done"],
                "scanned": total_scanned,
                "cowork_events": total_events,
                "from": start.date().isoformat(),
                "to": now.date().isoformat(),
            }
            await session.commit()
            return job.stats
        except Exception as exc:  # noqa: BLE001 - persisted for observability
            _progress["error"] = str(exc)
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = {"error": str(exc), "windows_done": _progress["windows_done"]}
            await session.commit()
            logger.exception("Backfill failed")
            raise
        finally:
            await client.aclose()
            _progress["running"] = False
