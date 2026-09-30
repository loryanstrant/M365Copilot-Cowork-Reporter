"""Queries that read the report's own operational record rather than its data.

Everything else in this app answers "what did people do with Cowork?". This
module answers "did the collection that was supposed to gather that actually
run?", which is a different question with a different table behind it.

It is a module rather than a handful of functions in the admin router because
the two ``job_runs`` vocabularies below have to be decided in exactly one
place. They are both untidy, both wider than they look, and a second copy of
either would drift within a release.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import JobRun

# ``job_runs.job_name`` is not an enum and never was, and the set it holds
# differs per repo — so this is a per-repo superset rather than a shared
# constant. This app writes five values: "scheduled" from the worker's timer,
# "manual" from Run now, "backfill" from the historical audit pull, and the two
# "csv-*" kinds from the upload path, which no other report in the suite has.
# It never writes "daily" or "users".
#
# Those two are Usage Reporter's, which also has production rows carrying
# "scheduled". They are mapped here anyway: the cost of carrying a label for a
# kind this app never writes is one dictionary line, and the cost of not
# carrying it is a row rendering as a raw string in whichever app is first to
# share a database.
#
# An unrecognised kind falls through to its raw value rather than being
# dropped. A run that happened and is not listed is worse than one labelled
# awkwardly — the page exists to answer "did it run", and a silent filter makes
# it lie by omission.
JOB_KIND_LABELS = {
    "scheduled": "Scheduled",
    "daily": "Scheduled",
    "manual": "Manual",
    "users": "User sync",
    "backfill": "Historical backfill",
    "csv-cowork-usage": "Usage CSV upload",
    "csv-credit-consumption": "Credit CSV upload",
}

# Seven status values exist across the suite, three of which are spellings of
# the same thing: "success", "completed" and "complete" all mean it worked and
# differ only by which module wrote the row — three words for one state, across
# four applications built from one template. ("preparing" is a backfill that has
# not started its first window yet.) This app writes only "success"; the rest
# are carried for the same reason the sibling job kinds are. The display layer
# absorbs all of it, and this is the one place the mapping is decided.
JOB_STATUS_STATE = {
    "success": "succeeded",
    "completed": "succeeded",
    "complete": "succeeded",
    "running": "running",
    "preparing": "running",
    "failed": "failed",
    "cancelled": "cancelled",
}


def _flatten_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """One level of nesting removed, keeping the group name on the key.

    A scheduled ingest writes ``{"users": {...}, "cost": {...}, "audit":
    {...}}`` — each collector's own return value nested under its name — while
    an upload writes flat counts. Flattening to the leaf key alone would make
    the two collide: ``rows`` means cost rows under ``cost`` and CSV lines at
    the top level, and a page that renders both as "rows" is worse than one
    that renders neither.

    So a nested leaf keeps its group ("cost.rows"), and a top-level key stays
    as it is. The label table below then maps the qualified names.
    """
    out: dict[str, Any] = {}
    for key, value in stats.items():
        if isinstance(value, dict):
            for leaf, inner in value.items():
                out[f"{key}.{leaf}"] = inner
        else:
            out[key] = value
    return out


async def scan_history(session: AsyncSession, *, limit: int = 100) -> list[dict[str, Any]]:
    """Every collection this report has run, newest first.

    ``job_runs`` has recorded this since the first release and nothing ever
    showed it, so "did last night's pull actually work?" had no answer in the
    UI — only in the container's logs, which the person asking cannot reach.
    """
    rows = (
        (
            await session.execute(
                select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    out: list[dict[str, Any]] = []
    for r in rows:
        stats = _flatten_stats(r.stats if isinstance(r.stats, dict) else {})
        duration = None
        if r.started_at and r.finished_at:
            duration = max(0, int((r.finished_at - r.started_at).total_seconds()))
        out.append(
            {
                "id": r.id,
                "kind": JOB_KIND_LABELS.get(r.job_name, r.job_name),
                "raw_kind": r.job_name,
                "state": JOB_STATUS_STATE.get(r.status, r.status),
                "raw_status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "duration_seconds": duration,
                # The error lives in stats for failed runs. Surfacing it is the
                # difference between a log people can act on and one that only
                # tells them to go and read the logs.
                "error": stats.get("error"),
                "stats": {k: v for k, v in stats.items() if k != "error"},
            }
        )
    return out


__all__ = ["JOB_KIND_LABELS", "JOB_STATUS_STATE", "scan_history"]
