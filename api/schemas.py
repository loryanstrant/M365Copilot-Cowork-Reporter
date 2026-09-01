"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


# --- auth ---------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserOut(BaseModel):
    username: str
    role: str


class AuthModeOut(BaseModel):
    entra_available: bool


# --- admin config -------------------------------------------------------
class AppConfigIn(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    # Write-only: only applied when a non-empty value is supplied.
    client_secret: str | None = None
    azure_subscription_ids: list[str] | None = None
    cost_rolling_window_days: int | None = None
    audit_backfill_days: int | None = None
    report_access_group_id: str | None = None
    schedule_interval_hours: int | None = None


class AppConfigOut(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    azure_subscription_ids: list[str] = []
    cost_rolling_window_days: int = 10
    audit_backfill_days: int = 30
    report_access_group_id: str | None = None
    schedule_interval_hours: int = 8
    configured: bool = False
    updated_at: datetime | None = None
    updated_by: str | None = None


class TestConnectionOut(BaseModel):
    ok: bool
    graph_token: bool = False
    arm_token: bool = False
    directory_read: bool = False
    audit_query: bool = False
    cost_read: bool = False
    directory_users: int | None = None
    detail: str | None = None


class IngestRunOut(BaseModel):
    status: str
    detail: str | None = None


class JobRunOut(BaseModel):
    id: int
    job_name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict | None = None


class StatusOut(BaseModel):
    configured: bool
    last_run: JobRunOut | None = None
    cowork_events: int
    daily_cost_rows: int
    cowork_usage_rows: int
    credit_rows: int
    directory_users: int


class UploadResultOut(BaseModel):
    rows: int
    imported: int
    skipped: int
    detail: str | None = None


# --- billing policy (chargeback mapping) --------------------------------
class BillingPolicyIn(BaseModel):
    resource_group: str
    billing_policy_name: str | None = None
    cost_centre: str | None = None
    business_owner: str | None = None
    project: str | None = None
    notes: str | None = None


class BillingPolicyOut(BillingPolicyIn):
    updated_at: datetime | None = None
    updated_by: str | None = None


# --- metrics ------------------------------------------------------------
class KpiOut(BaseModel):
    total_cost: float
    currency: str | None = None
    total_credits: float
    total_tasks: int
    active_users: int
    cowork_events: int


class CostByGroupOut(BaseModel):
    resource_group: str | None
    cost_centre: str | None
    project: str | None
    cost: float


class CostTrendOut(BaseModel):
    cost_date: date
    cost: float


class UsageByUserOut(BaseModel):
    user_principal_name: str
    display_name: str | None
    department: str | None
    job_title: str | None
    company_name: str | None
    office_location: str | None
    country: str | None
    manager_name: str | None
    total_tasks: int
    scheduled_tasks: int
    user_initiated_tasks: int
    active_days: int
    last_activity_date: datetime | None


class DirectoryUserOut(BaseModel):
    user_principal_name: str | None
    display_name: str | None
    job_title: str | None
    department: str | None
    company_name: str | None
    office_location: str | None
    city: str | None
    country: str | None
    manager_name: str | None
    user_type: str | None
    account_enabled: bool | None


class UsageTrendOut(BaseModel):
    period_days: int
    active_users: int
    total_tasks: int
