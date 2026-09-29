"""SQL that differs between Postgres and SQLite.

tests/conftest.py forces SQLite so the suite needs no database service. That is
a good trade, but it means any SQL whose spelling differs between the two is
untested against the one that actually runs in production.

This module closes that specific gap by compiling expressions for each dialect
and asserting the text. It exists because of a real escape: the personal page
and the executive briefing both counted JSON array lengths with
``json_array_length``, which SQLite has and Postgres has only for its ``json``
type — the columns are JSONB, so every request 500'd against a real database
while all 128 tests passed.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from api.routers.metrics import _json_len
from shared.models import CoworkEvent


def _sql(expr, dialect) -> str:
    return str(expr.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize(
    ("dialect", "expected", "forbidden"),
    [
        (postgresql.dialect(), "jsonb_array_length", "json_array_length("),
        (sqlite.dialect(), "json_array_length", "jsonb_array_length"),
    ],
    ids=["postgresql", "sqlite"],
)
def test_json_array_length_is_spelled_for_the_dialect(dialect, expected, forbidden):
    sql = _sql(select(_json_len(CoworkEvent.tools)), dialect)
    assert expected in sql
    # jsonb_array_length contains json_array_length as a substring, so the
    # negative check has to be anchored on the opening bracket for Postgres.
    if forbidden == "json_array_length(":
        assert "(json_array_length(" not in sql and not sql.count(" json_array_length(")
    else:
        assert forbidden not in sql


@pytest.mark.parametrize(
    "dialect", [postgresql.dialect(), sqlite.dialect()], ids=["postgresql", "sqlite"]
)
def test_a_null_json_column_counts_as_zero_in_both_dialects(dialect):
    """The columns are nullable and usually null, so this is the common path."""
    sql = _sql(select(_json_len(CoworkEvent.accessed_resources)), dialect)
    assert "coalesce" in sql.lower()
    assert "IS NULL" in sql
