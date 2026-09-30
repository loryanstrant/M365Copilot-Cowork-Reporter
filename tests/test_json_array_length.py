"""Counting the lists on a Cowork event, when the list is a JSON null.

The audit feed writes the JSON value ``null`` — not SQL NULL — into ``tools``
and ``accessed_resources`` for an event that used no tools or touched no files.
On the tenant this was found in, that was 25 of 80 rows and 73 of 80.

PostgreSQL's ``jsonb_array_length`` raises ``cannot get array length of a
scalar`` on that value, so the executive briefing and the personal activity
page both returned 500 against real data. **Every test passed**, because these
run on SQLite, whose ``json_array_length`` answers 0 for the same input rather
than raising — and because the seeder only ever writes arrays.

So a behavioural test on SQLite cannot fail for the right reason. This asserts
the *generated SQL* instead: the Postgres dialect must ask what the value is
before asking how long it is.
"""
from __future__ import annotations

from sqlalchemy.dialects import postgresql, sqlite

from api.routers.metrics import _json_len
from shared.models import CoworkEvent


def _compile(dialect) -> str:
    return str(
        _json_len(CoworkEvent.tools).compile(
            dialect=dialect, compile_kwargs={"literal_binds": True}
        )
    )


def test_postgres_checks_the_type_before_taking_a_length():
    sql = _compile(postgresql.dialect())
    assert "jsonb_typeof" in sql, (
        "Without a type check, a JSON null raises 'cannot get array length of "
        "a scalar' and the endpoint 500s. This is the regression."
    )
    assert "jsonb_array_length" in sql


def test_postgres_still_measures_real_arrays():
    sql = _compile(postgresql.dialect()).lower()
    assert "case when" in sql and "else 0" in sql


def test_sqlite_is_left_alone():
    """SQLite's json_array_length already answers 0 for a JSON null, so it
    needs no guard — and adding jsonb_* there would not even compile."""
    sql = _compile(sqlite.dialect())
    assert "json_array_length" in sql
    assert "jsonb_typeof" not in sql
