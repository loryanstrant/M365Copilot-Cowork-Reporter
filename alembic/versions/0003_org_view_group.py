"""Add app_config.org_view_group_id.

Membership of this Entra group unlocks the organisation-wide view. It is
deliberately separate from ``report_access_group_id``, which governs whether
someone can open the report at all — repurposing that one would have handed a
personal view to people a tenant had explicitly excluded.

Left NULL on upgrade, which means "org view open to everyone who can sign in".
That matches the behaviour before the personal view existed, so upgrading does
not silently lock anyone out.

The existence check is not belt-and-braces: ``0001_initial`` in this repo builds
the schema with ``Base.metadata.create_all``, i.e. from the live ORM models
rather than a frozen snapshot. A fresh database therefore already has every
column the models currently declare — including this one — while a database
created before this field existed genuinely needs it added. Any migration added
to this repo has to cope with both.

Revision ID: 0003_org_view_group
Revises: 0002_user_profile
Create Date: 2026-09-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_org_view_group"
down_revision = "0002_user_profile"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    bind = op.get_bind()
    return "org_view_group_id" in {
        c["name"] for c in sa.inspect(bind).get_columns("app_config")
    }


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            "app_config", sa.Column("org_view_group_id", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    if _has_column():
        op.drop_column("app_config", "org_view_group_id")
