"""Add app_config.admin_group_id.

Members of this Entra group get administrator rights when they sign in with
Entra ID, so administering the app no longer means sharing one username and
password between several people.

Left NULL on upgrade, which grants admin to nobody. That is deliberately the
opposite of ``org_view_group_id``, where NULL means "open to everyone": the org
view was open before that field existed and must not close on upgrade, whereas
administration has always been an explicit grant and must not open on upgrade.
The local admin account is unaffected either way, and is the account used to
set this field in the first place.

No guard is needed against the column already existing. ``0001_initial`` was
frozen to an explicit schema snapshot (issue #5), so a fresh database arrives
here with exactly the columns 0001 declares and not whatever the ORM happens
to declare today — unlike ``0003_org_view_group``, which was written while
0001 still built the schema with ``create_all`` and carries an inspector guard
for that reason.

Revision ID: 0004_admin_group
Revises: 0003_org_view_group
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_admin_group"
down_revision = "0003_org_view_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("admin_group_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_config", "admin_group_id")
