"""initial cowork reporting schema

An explicit snapshot, deliberately NOT ``Base.metadata.create_all``.

This migration used to build the schema from the live ORM metadata. That meant
it created whatever the models declared *today* rather than what they declared
at this revision, so on a fresh database every later migration found its columns
already present and collided with them — see issue #3, where 0002 failed with
DuplicateColumn and, because Alembic runs the chain in one transaction, rolled
0001 back with it and left the database with no tables at all.

Freezing it here means later migrations apply against a known starting shape.
Do not reintroduce ``create_all``: any column added to a model in future would
silently appear here and break the next migration in exactly the same way.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('app_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Text(), nullable=True),
    sa.Column('client_id', sa.Text(), nullable=True),
    sa.Column('client_secret_encrypted', sa.Text(), nullable=True),
    sa.Column('azure_subscription_ids', postgresql.ARRAY(sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
    sa.Column('cost_rolling_window_days', sa.Integer(), nullable=False),
    sa.Column('audit_backfill_days', sa.Integer(), nullable=False),
    sa.Column('report_access_group_id', sa.Text(), nullable=True),
    sa.Column('schedule_interval_hours', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_by', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('app_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_app_users_username'), 'app_users', ['username'], unique=True)
    op.create_table('dim_billing_policy',
    sa.Column('resource_group', sa.Text(), nullable=False),
    sa.Column('billing_policy_name', sa.Text(), nullable=True),
    sa.Column('cost_centre', sa.Text(), nullable=True),
    sa.Column('business_owner', sa.Text(), nullable=True),
    sa.Column('project', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_by', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('resource_group')
    )
    op.create_table('dim_user',
    sa.Column('user_id', sa.Text(), nullable=False),
    sa.Column('upn', sa.Text(), nullable=True),
    sa.Column('email', sa.Text(), nullable=True),
    sa.Column('display_name', sa.Text(), nullable=True),
    sa.Column('job_title', sa.Text(), nullable=True),
    sa.Column('company_name', sa.Text(), nullable=True),
    sa.Column('department', sa.Text(), nullable=True),
    sa.Column('office_location', sa.Text(), nullable=True),
    sa.Column('country', sa.Text(), nullable=True),
    sa.Column('manager_id', sa.Text(), nullable=True),
    sa.Column('account_enabled', sa.Boolean(), nullable=True),
    sa.Column('user_type', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_dim_user_manager_id'), 'dim_user', ['manager_id'], unique=False)
    op.create_index(op.f('ix_dim_user_upn'), 'dim_user', ['upn'], unique=False)
    op.create_table('fact_cowork_event',
    sa.Column('event_id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_id', sa.Text(), nullable=True),
    sa.Column('user_principal_name', sa.Text(), nullable=True),
    sa.Column('operation', sa.Text(), nullable=True),
    sa.Column('app_host', sa.Text(), nullable=True),
    sa.Column('app_identity', sa.Text(), nullable=True),
    sa.Column('agent_name', sa.Text(), nullable=True),
    sa.Column('thread_id', sa.Text(), nullable=True),
    sa.Column('client_ip', sa.Text(), nullable=True),
    sa.Column('tools', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.Column('accessed_resources', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.Column('prompt_message_count', sa.Integer(), nullable=True),
    sa.Column('response_message_count', sa.Integer(), nullable=True),
    sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('event_id')
    )
    op.create_index(op.f('ix_fact_cowork_event_created_at'), 'fact_cowork_event', ['created_at'], unique=False)
    op.create_index(op.f('ix_fact_cowork_event_thread_id'), 'fact_cowork_event', ['thread_id'], unique=False)
    op.create_index(op.f('ix_fact_cowork_event_user_id'), 'fact_cowork_event', ['user_id'], unique=False)
    op.create_index(op.f('ix_fact_cowork_event_user_principal_name'), 'fact_cowork_event', ['user_principal_name'], unique=False)
    op.create_table('fact_cowork_usage',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('report_refresh_date', sa.Date(), nullable=False),
    sa.Column('report_period', sa.Integer(), nullable=True),
    sa.Column('user_principal_name', sa.Text(), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=True),
    sa.Column('total_tasks', sa.Integer(), nullable=False),
    sa.Column('scheduled_tasks', sa.Integer(), nullable=False),
    sa.Column('user_initiated_tasks', sa.Integer(), nullable=False),
    sa.Column('active_days', sa.Integer(), nullable=False),
    sa.Column('last_activity_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('report_refresh_date', 'user_principal_name', 'report_period', name='uq_cowork_usage')
    )
    op.create_index(op.f('ix_fact_cowork_usage_report_period'), 'fact_cowork_usage', ['report_period'], unique=False)
    op.create_index(op.f('ix_fact_cowork_usage_report_refresh_date'), 'fact_cowork_usage', ['report_refresh_date'], unique=False)
    op.create_index(op.f('ix_fact_cowork_usage_user_principal_name'), 'fact_cowork_usage', ['user_principal_name'], unique=False)
    op.create_table('fact_credit_consumption',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('as_of_date', sa.Date(), nullable=False),
    sa.Column('scope_type', sa.Text(), nullable=False),
    sa.Column('scope_id', sa.Text(), nullable=True),
    sa.Column('scope_name', sa.Text(), nullable=True),
    sa.Column('license_type', sa.Text(), nullable=True),
    sa.Column('credits_consumed', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('prepaid_consumed', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('paygo_consumed', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('user_count', sa.Integer(), nullable=True),
    sa.Column('last_activity_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('as_of_date', 'scope_type', 'scope_id', 'license_type', name='uq_credit_consumption')
    )
    op.create_index(op.f('ix_fact_credit_consumption_as_of_date'), 'fact_credit_consumption', ['as_of_date'], unique=False)
    op.create_index(op.f('ix_fact_credit_consumption_scope_id'), 'fact_credit_consumption', ['scope_id'], unique=False)
    op.create_index(op.f('ix_fact_credit_consumption_scope_type'), 'fact_credit_consumption', ['scope_type'], unique=False)
    op.create_table('fact_daily_cost',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cost_date', sa.Date(), nullable=False),
    sa.Column('subscription_id', sa.Text(), nullable=False),
    sa.Column('resource_group', sa.Text(), nullable=True),
    sa.Column('service_name', sa.Text(), nullable=True),
    sa.Column('meter_category', sa.Text(), nullable=True),
    sa.Column('meter_name', sa.Text(), nullable=True),
    sa.Column('cost', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cost_date', 'subscription_id', 'resource_group', 'meter_category', 'meter_name', name='uq_daily_cost')
    )
    op.create_index(op.f('ix_fact_daily_cost_cost_date'), 'fact_daily_cost', ['cost_date'], unique=False)
    op.create_index(op.f('ix_fact_daily_cost_resource_group'), 'fact_daily_cost', ['resource_group'], unique=False)
    op.create_index(op.f('ix_fact_daily_cost_subscription_id'), 'fact_daily_cost', ['subscription_id'], unique=False)
    op.create_table('ingest_state',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('watermark', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_status', sa.Text(), nullable=True),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('job_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('job_name', sa.Text(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_runs_job_name'), 'job_runs', ['job_name'], unique=False)


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("ingest_state")
    op.drop_table("fact_daily_cost")
    op.drop_table("fact_credit_consumption")
    op.drop_table("fact_cowork_usage")
    op.drop_table("fact_cowork_event")
    op.drop_table("dim_user")
    op.drop_table("dim_billing_policy")
    op.drop_table("app_users")
    op.drop_table("app_config")
