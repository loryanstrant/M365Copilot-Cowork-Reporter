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


# --------------------------------------------------------------------------- #
# Telling "no credits" apart from "we did not find the credits column"
#
# A tolerant parser fails silently: an unrecognised header reads exactly like a
# column of zeroes, and the tenant gets a credit report of 0.0000 with no way
# to know which it was. On the live tenant this produced six rows of zeroes and
# cost an afternoon to diagnose from the database. The import now says so.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_an_unrecognised_credits_column_is_reported_not_silently_zero(session):
    csv = (
        b"User Principal Name,Display Name,Widgets Burned\n"
        b"ada@contoso.com,Ada,42\n"
    )
    result = await import_credit_consumption(session, csv)
    assert result["imported"] == 1
    assert result["detail"] is not None
    assert "Widgets Burned" in result["detail"]


@pytest.mark.asyncio
async def test_a_recognised_credits_column_reports_nothing(session):
    csv = (
        b"User Principal Name,Display Name,Credits Consumed\n"
        b"ada@contoso.com,Ada,0\n"
    )
    result = await import_credit_consumption(session, csv)
    assert result["detail"] is None, "a genuine zero is not a parsing problem"


@pytest.mark.asyncio
async def test_a_ragged_row_does_not_break_the_diagnostic(session):
    """DictReader files surplus cells under a None key; the message must cope."""
    csv = (
        b"User Principal Name,Display Name\n"
        b"ada@contoso.com,Ada,stray,cells\n"
    )
    result = await import_credit_consumption(session, csv)
    assert result["imported"] == 1
    assert "User Principal Name" in result["detail"]


# --------------------------------------------------------------------------- #
# The header the real export actually uses
#
# The live tenant's upload landed six rows with a name on each and no figure
# anywhere: the parser matched "User Principal Name" and "Display Name" and
# none of its five candidate spellings for the number. The admin centre calls
# that column **Monthly Credits Used**, which was not among them.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_monthly_credits_used_is_the_admin_centre_spelling(session):
    csv = (
        b"User Principal Name,Display Name,Monthly Credits Used\n"
        b"ada@contoso.com,Ada Lovelace,1234.5\n"
    )
    result = await import_credit_consumption(session, csv)
    assert result["imported"] == 1
    row = await session.scalar(select(CreditConsumption))
    assert float(row.credits_consumed) == 1234.5
    # and it is a match, so the "we found no figures" warning stays quiet
    assert result["detail"] is None


@pytest.mark.asyncio
async def test_the_header_match_ignores_case_and_punctuation(session):
    """Matching is normalised, so one entry covers the export's variants."""
    csv = (
        b"userPrincipalName,displayName,monthly_credits_used\n"
        b"ada@contoso.com,Ada,7\n"
    )
    result = await import_credit_consumption(session, csv)
    row = await session.scalar(select(CreditConsumption))
    assert float(row.credits_consumed) == 7
    assert result["detail"] is None
