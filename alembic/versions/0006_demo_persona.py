"""Add app_config.demo_persona_user_id.

Loading demo data binds the local admin account to one of the seeded directory
users, and this is where that binding lives. Without it the personal pages
cannot be reached at all without an Entra sign-in — ``has_personal_view`` needs
a directory identity and the password admin has none — so anyone evaluating the
product with demo data never sees the pages the README advertises.

It is a column on ``app_config`` rather than a row in ``ingest_state``. The
binding is configuration and belongs beside the rest of it; ``ingest_state``
holds collector watermarks, and an identity binding filed there is invisible to
anyone reading the model and misleading to anyone reading the table. The same
shape is used by all four solutions in this suite.

NULL on upgrade, and set only by an explicit demo seed. It is cleared when demo
data is cleared and when a real ingest succeeds, so a tenant that seeds, looks
and then goes live is left exactly where it started.

Revision ID: 0006_demo_persona
Revises: 0005_copilot_license
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_demo_persona"
down_revision = "0005_copilot_license"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config", sa.Column("demo_persona_user_id", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("app_config", "demo_persona_user_id")
