"""enrich dim_user with full profile fields + extension attributes

Revision ID: 0002_user_profile
Revises: 0001_initial
Create Date: 2026-09-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_user_profile"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_COLUMNS = [
    "given_name", "surname", "city", "state", "usage_location",
    "employee_id", "employee_type", "manager_name",
    *[f"ext{i}" for i in range(1, 16)],
]


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns("dim_user")}


def upgrade() -> None:
    # 0001_initial builds the schema with ``Base.metadata.create_all``, i.e. from
    # the live ORM models rather than a frozen snapshot. On a fresh database it
    # therefore already creates whatever columns the models carry today —
    # including these — and adding them again fails with DuplicateColumn. On a
    # database created before those model fields existed, they are genuinely
    # missing and do need adding. Check, rather than assume either way.
    present = _existing_columns()
    for col in _COLUMNS:
        if col not in present:
            op.add_column("dim_user", sa.Column(col, sa.Text(), nullable=True))


def downgrade() -> None:
    present = _existing_columns()
    for col in _COLUMNS:
        if col in present:
            op.drop_column("dim_user", col)
