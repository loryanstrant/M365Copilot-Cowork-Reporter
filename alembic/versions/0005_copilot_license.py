"""Add dim_user.has_copilot_license.

Cowork Reporter had no notion of a Copilot licence. It could report what people
did, but not how many of the people a tenant is paying for were doing anything
at all — which is the question a renewal turns on, and the one the Tenant users
listing now answers.

The flag is derived at ingest from the tenant's own ``subscribedSkus`` rather
than from a configured SKU list, so Microsoft 365 E7 and any future
Copilot-bearing SKU count without anyone editing a setting. See
``worker/licensing.py``.

Nullable on purpose, and left NULL on upgrade. NULL means "never determined" —
the row predates licence detection, or no sync has run since — which is a
different statement from False, "we asked Graph and this person is not
licensed". Backfilling NULL to False here would assert the second on no
evidence, and the Tenant users filter would then quietly hide everyone until
the first successful ingest.

Indexed because the filtered Tenant users listing selects on it.

Revision ID: 0005_copilot_license
Revises: 0004_admin_group
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_copilot_license"
down_revision = "0004_admin_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dim_user", sa.Column("has_copilot_license", sa.Boolean(), nullable=True)
    )
    op.create_index(
        "ix_dim_user_has_copilot_license", "dim_user", ["has_copilot_license"]
    )


def downgrade() -> None:
    op.drop_index("ix_dim_user_has_copilot_license", table_name="dim_user")
    op.drop_column("dim_user", "has_copilot_license")
