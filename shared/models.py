"""SQLAlchemy 2.0 ORM models — Cowork reporting star schema.

Two data planes that are never blended (joined on user only):

* **Consumption** — money/credits:
    - ``fact_daily_cost``       Azure Cost Management Query API (app-only, automated)
    - ``fact_credit_consumption`` admin-centre Cost Management / Credits CSV upload
* **Usage** — tasks/adoption:
    - ``fact_cowork_usage``     admin-centre Cowork usage report CSV upload
    - ``fact_cowork_event``     Purview audit ``CopilotInteraction`` (app-only, automated)

Dimensions: ``dim_user`` (Entra), ``dim_billing_policy`` (UI-editable — the
chargeback mapping Microsoft doesn't provide).

Postgres-specific column types (JSONB, ARRAY) fall back to portable JSON variants
under SQLite so the test-suite can run without a Postgres instance.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base

# Portable column types: JSONB/ARRAY on Postgres, plain JSON on SQLite (tests).
JsonType = JSONB().with_variant(JSON(), "sqlite")
StrArray = ARRAY(Text).with_variant(JSON(), "sqlite")


# ======================================================================
# CONSUMPTION plane
# ======================================================================
class DailyCost(Base):
    """One row per (day, subscription, resource group, meter) — Azure cost.

    Sourced from the Cost Management Query API grouped by ResourceGroup +
    MeterCategory, granularity Daily. Idempotent on the natural key so the
    trailing rolling-window replace (cost data restates) is safe.
    """

    __tablename__ = "fact_daily_cost"
    __table_args__ = (
        UniqueConstraint(
            "cost_date",
            "subscription_id",
            "resource_group",
            "meter_category",
            "meter_name",
            name="uq_daily_cost",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cost_date: Mapped[date] = mapped_column(Date, index=True)
    subscription_id: Mapped[str] = mapped_column(Text, index=True)
    resource_group: Mapped[str | None] = mapped_column(Text, index=True)
    service_name: Mapped[str | None] = mapped_column(Text)
    meter_category: Mapped[str | None] = mapped_column(Text)
    meter_name: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    currency: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CreditConsumption(Base):
    """Copilot Credit consumption snapshot (admin-centre Cost Management CSV).

    ``scope_type`` distinguishes the export shape: ``service`` (e.g. Cowork),
    ``user``, ``group``, or ``summary``. There is no API for this data, so it is
    uploaded as CSV; the natural key makes re-uploads idempotent.
    """

    __tablename__ = "fact_credit_consumption"
    __table_args__ = (
        UniqueConstraint(
            "as_of_date", "scope_type", "scope_id", "license_type",
            name="uq_credit_consumption",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    # service | user | group | summary
    scope_type: Mapped[str] = mapped_column(Text, index=True)
    scope_id: Mapped[str | None] = mapped_column(Text, index=True)
    scope_name: Mapped[str | None] = mapped_column(Text)
    # PrepaidCapacityPack | PayAsYouGo | combined
    license_type: Mapped[str | None] = mapped_column(Text)
    credits_consumed: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    prepaid_consumed: Mapped[float | None] = mapped_column(Numeric(18, 4))
    paygo_consumed: Mapped[float | None] = mapped_column(Numeric(18, 4))
    user_count: Mapped[int | None] = mapped_column(Integer)
    last_activity_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text, default="csv")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ======================================================================
# USAGE plane
# ======================================================================
class CoworkUsage(Base):
    """Per-user Cowork adoption snapshot (admin-centre Cowork usage CSV).

    Mirrors the admin-centre report columns: total / scheduled / user-initiated
    tasks, active days, last activity — for a given report window. No API exists,
    so uploaded as CSV; idempotent on (refresh date, user, period).
    """

    __tablename__ = "fact_cowork_usage"
    __table_args__ = (
        UniqueConstraint(
            "report_refresh_date", "user_principal_name", "report_period",
            name="uq_cowork_usage",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_refresh_date: Mapped[date] = mapped_column(Date, index=True)
    # 7 | 28 | 90 | 180 (the admin report's rolling windows), or null for a
    # custom date-range export.
    report_period: Mapped[int | None] = mapped_column(Integer, index=True)
    user_principal_name: Mapped[str] = mapped_column(Text, index=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_tasks: Mapped[int] = mapped_column(Integer, default=0)
    user_initiated_tasks: Mapped[int] = mapped_column(Integer, default=0)
    active_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text, default="csv")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CoworkEvent(Base):
    """One Purview audit ``CopilotInteraction`` row identified as Cowork.

    Identification (validated live against the Avanoso tenant): a row is Cowork
    when ``CopilotEventData.AppHost == 'cowork'`` OR
    ``AppIdentity == 'Copilot.M365Copilot.CoworkChat'``.

    Audit answers *who / when / what-touched* — never task volume (use
    ``CoworkUsage``) or cost (use the consumption plane). ``Messages`` carries
    IDs + an ``isPrompt`` flag only, never prompt text.
    """

    __tablename__ = "fact_cowork_event"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    user_id: Mapped[str | None] = mapped_column(Text, index=True)
    user_principal_name: Mapped[str | None] = mapped_column(Text, index=True)
    operation: Mapped[str | None] = mapped_column(Text)
    app_host: Mapped[str | None] = mapped_column(Text)
    app_identity: Mapped[str | None] = mapped_column(Text)
    agent_name: Mapped[str | None] = mapped_column(Text)
    thread_id: Mapped[str | None] = mapped_column(Text, index=True)
    client_ip: Mapped[str | None] = mapped_column(Text)
    # Names of AI system plugins/tools invoked (e.g. tool_search_tool).
    tools: Mapped[list | None] = mapped_column(JsonType)
    # Resources Cowork touched (id, name, sensitivityLabelId, XPIADetected...).
    accessed_resources: Mapped[list | None] = mapped_column(JsonType)
    prompt_message_count: Mapped[int | None] = mapped_column(Integer)
    response_message_count: Mapped[int | None] = mapped_column(Integer)
    raw_json: Mapped[dict | None] = mapped_column(JsonType)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ======================================================================
# DIMENSIONS
# ======================================================================
class DirectoryUser(Base):
    """A directory user (Entra) — org context for chargeback and adoption."""

    __tablename__ = "dim_user"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    upn: Mapped[str | None] = mapped_column(Text, index=True)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    office_location: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    manager_id: Mapped[str | None] = mapped_column(Text, index=True)
    account_enabled: Mapped[bool | None] = mapped_column(Boolean)
    user_type: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BillingPolicy(Base):
    """UI-editable mapping: resource group -> billing policy -> chargeback.

    This is the gap Microsoft's tooling doesn't fill: it turns a *cost* view into
    a *chargeback* view. Human-maintained reference data, edited in the admin UI.
    """

    __tablename__ = "dim_billing_policy"

    resource_group: Mapped[str] = mapped_column(Text, primary_key=True)
    billing_policy_name: Mapped[str | None] = mapped_column(Text)
    cost_centre: Mapped[str | None] = mapped_column(Text)
    business_owner: Mapped[str | None] = mapped_column(Text)
    project: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(Text)


# ======================================================================
# OPERATIONAL
# ======================================================================
class AppConfig(Base):
    """Single-row admin settings. Client secret stored Fernet-encrypted."""

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # Graph + ARM app registration (app-only). The SAME registration is used for
    # Purview audit (AuditLogsQuery.Read.All), directory users (User.Read.All)
    # and Azure Cost Management (Cost Management Reader on the subscription).
    tenant_id: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(Text)
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    # Azure subscriptions to pull cost from (Cost Management Query API).
    azure_subscription_ids: Mapped[list[str]] = mapped_column(StrArray, default=list)
    # Rolling-window replace: re-pull & replace this many trailing days each run.
    cost_rolling_window_days: Mapped[int] = mapped_column(Integer, default=10)
    # First-run look-back for the Purview audit collector.
    audit_backfill_days: Mapped[int] = mapped_column(Integer, default=30)
    # Optional Entra SSO gate for read-only viewers.
    report_access_group_id: Mapped[str | None] = mapped_column(Text)
    # Recurring ingest cadence (hours). Cost refreshes every 4h; 6-8h recommended.
    schedule_interval_hours: Mapped[int] = mapped_column(Integer, default=8)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(Text)


class IngestState(Base):
    """Per-key watermark + last status for incremental ingest/observability."""

    __tablename__ = "ingest_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict | None] = mapped_column(JsonType)


class JobRun(Base):
    """One record per ingestion/upload run for observability."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(Text, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="running")
    stats: Mapped[dict | None] = mapped_column(JsonType)


class AppUser(Base):
    """Local login account for the password gate."""

    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="viewer")  # admin | viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
