"""CSV import tests — the two admin-centre exports."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from shared.models import CoworkUsage, CreditConsumption
from worker.csv_import import import_cowork_usage, import_credit_consumption

USAGE_CSV = (
    b"User Principal Name,Display Name,Total Tasks,Scheduled Tasks,"
    b"User-initiated Tasks,Active Days,Last Activity Date\n"
    b"loryan.strant@avanoso.com,Loryan Strant,8,0,8,3,2026-08-26\n"
    b"ping.lim@avanoso.com,Ping Lim,1,0,1,1,2026-08-25\n"
)

CREDIT_CSV = (
    b"User Principal Name,Credits Consumed,PayGo Consumed\n"
    b"loryan.strant@avanoso.com,250.5,40\n"
)


@pytest.mark.asyncio
async def test_import_cowork_usage(session):
    result = await import_cowork_usage(session, USAGE_CSV, report_period=28)
    assert result["imported"] == 2
    total = await session.scalar(select(func.sum(CoworkUsage.total_tasks)))
    assert int(total) == 9


@pytest.mark.asyncio
async def test_cowork_usage_is_idempotent(session):
    await import_cowork_usage(session, USAGE_CSV, report_period=28)
    await import_cowork_usage(session, USAGE_CSV, report_period=28)
    count = await session.scalar(select(func.count()).select_from(CoworkUsage))
    assert count == 2  # re-upload updates, does not duplicate


@pytest.mark.asyncio
async def test_import_credit_consumption(session):
    result = await import_credit_consumption(session, CREDIT_CSV, scope_type="user")
    assert result["imported"] == 1
    row = await session.scalar(select(CreditConsumption))
    assert float(row.credits_consumed) == 250.5
    assert row.scope_type == "user"
