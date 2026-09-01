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


def upgrade() -> None:
    for col in _COLUMNS:
        op.add_column("dim_user", sa.Column(col, sa.Text(), nullable=True))


def downgrade() -> None:
    for col in _COLUMNS:
        op.drop_column("dim_user", col)
