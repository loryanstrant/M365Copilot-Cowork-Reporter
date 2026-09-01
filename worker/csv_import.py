"""CSV import for the two admin-centre exports that have no API.

Microsoft ships **no** programmatic endpoint for Cowork task metrics or Copilot
Credit consumption — both are admin-centre UI reports with a CSV export button.
An admin uploads those CSVs here; parsing is tolerant of header-name variants and
idempotent on each table's natural key, so re-uploading a fresher export just
updates the rows.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import CoworkUsage, CreditConsumption, JobRun
from shared.upsert import bulk_upsert

logger = logging.getLogger("worker.csv_import")


class CsvImportError(ValueError):
    """Raised when a CSV cannot be parsed into the expected shape."""


def _norm(header: str) -> str:
    """Normalise a header for matching: lowercase, strip non-alphanumerics."""
    return re.sub(r"[^a-z0-9]", "", (header or "").lower())


def _pick(row: dict[str, str], *candidates: str) -> str | None:
    """Return the first non-empty value whose normalised header matches."""
    norm_row = {_norm(k): v for k, v in row.items()}
    for cand in candidates:
        val = norm_row.get(_norm(cand))
        if val not in (None, ""):
            return val
    return None


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return 0


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _to_date(value: Any) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    d = _to_date(value)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) if d else None


def _read_rows(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvImportError("CSV has no header row.")
    return [row for row in reader]


# --- Cowork usage report -----------------------------------------------
async def import_cowork_usage(
    session: AsyncSession,
    content: bytes,
    *,
    report_period: int | None = None,
    report_refresh_date: date | None = None,
) -> dict[str, Any]:
    """Import an admin-centre Cowork usage report CSV into ``fact_cowork_usage``."""
    rows = _read_rows(content)
    default_refresh = report_refresh_date or date.today()
    out: list[dict[str, Any]] = []
    skipped = 0
    for r in rows:
        upn = _pick(r, "User Principal Name", "UserPrincipalName", "User ID",
                    "UserId", "UPN", "User")
        if not upn:
            skipped += 1
            continue
        out.append({
            "report_refresh_date": _to_date(
                _pick(r, "Report Refresh Date", "ReportRefreshDate")
            ) or default_refresh,
            "report_period": _to_int(_pick(r, "Report Period", "ReportPeriod"))
            or report_period,
            "user_principal_name": upn,
            "display_name": _pick(r, "Display Name", "DisplayName"),
            "total_tasks": _to_int(_pick(r, "Total Tasks", "TotalTasks", "Total")),
            "scheduled_tasks": _to_int(
                _pick(r, "Scheduled Tasks", "ScheduledTasks", "Scheduled")
            ),
            "user_initiated_tasks": _to_int(
                _pick(r, "User-initiated Tasks", "User Initiated Tasks",
                      "UserInitiatedTasks", "User-initiated")
            ),
            "active_days": _to_int(_pick(r, "Active Days", "ActiveDays")),
            "last_activity_date": _to_dt(
                _pick(r, "Last Activity Date", "LastActivityDate", "Last activity date")
            ),
            "source": "csv",
        })
    inserted = await bulk_upsert(
        session, CoworkUsage, out,
        index_elements=["report_refresh_date", "user_principal_name", "report_period"],
        update_keys=[
            "display_name", "total_tasks", "scheduled_tasks",
            "user_initiated_tasks", "active_days", "last_activity_date", "source",
        ],
    )
    session.add(JobRun(
        job_name="csv-cowork-usage", status="success",
        finished_at=datetime.now(timezone.utc),
        stats={"rows": len(rows), "imported": inserted, "skipped": skipped},
    ))
    await session.commit()
    return {"rows": len(rows), "imported": inserted, "skipped": skipped}


# --- Credit consumption -------------------------------------------------
async def import_credit_consumption(
    session: AsyncSession,
    content: bytes,
    *,
    scope_type: str = "user",
    as_of_date: date | None = None,
) -> dict[str, Any]:
    """Import an admin-centre Cost Management / Credits CSV into
    ``fact_credit_consumption``. ``scope_type`` selects the export shape
    (``user`` | ``service`` | ``group`` | ``summary``)."""
    rows = _read_rows(content)
    default_as_of = as_of_date or date.today()
    out: list[dict[str, Any]] = []
    skipped = 0
    for r in rows:
        scope_id = _pick(
            r, "User Principal Name", "UserPrincipalName", "User", "UPN",
            "Service", "Service Name", "ServiceName", "Agent", "Group", "Group Name",
        )
        if not scope_id and scope_type != "summary":
            skipped += 1
            continue
        out.append({
            "as_of_date": _to_date(_pick(r, "As Of Date", "AsOf", "Date", "asOf"))
            or default_as_of,
            "scope_type": scope_type,
            "scope_id": scope_id or scope_type,
            "scope_name": _pick(r, "Display Name", "DisplayName", "Name",
                                "Service Name", "ServiceName"),
            "license_type": _pick(r, "License Type", "LicenseType", "Plan",
                                  "Billing Type") or "combined",
            "credits_consumed": _to_float(
                _pick(r, "Credits Consumed", "ConsumedCredits", "Consumed Credits",
                      "Credits", "Total Credits")
            ) or 0,
            "prepaid_consumed": _to_float(
                _pick(r, "Prepaid Consumed", "PrepaidConsumed", "Prepaid")
            ),
            "paygo_consumed": _to_float(
                _pick(r, "PayGo Consumed", "PaygoConsumed", "Pay-as-you-go", "PayGo")
            ),
            "user_count": _to_int(_pick(r, "User Count", "UserCount", "Users"))
            or None,
            "last_activity_date": _to_dt(
                _pick(r, "Last Activity Date", "LastActivityDate")
            ),
            "source": "csv",
        })
    inserted = await bulk_upsert(
        session, CreditConsumption, out,
        index_elements=["as_of_date", "scope_type", "scope_id", "license_type"],
        update_keys=[
            "scope_name", "credits_consumed", "prepaid_consumed",
            "paygo_consumed", "user_count", "last_activity_date", "source",
        ],
    )
    session.add(JobRun(
        job_name="csv-credit-consumption", status="success",
        finished_at=datetime.now(timezone.utc),
        stats={"rows": len(rows), "imported": inserted, "skipped": skipped,
               "scope_type": scope_type},
    ))
    await session.commit()
    return {"rows": len(rows), "imported": inserted, "skipped": skipped}
