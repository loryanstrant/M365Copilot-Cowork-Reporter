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
    # Entra's display name. None for the password admin and for tokens issued
    # before display names were carried, so the UI falls back to the username.
    display_name: str | None = None
    # The signed-in person's UPN. Reported separately from ``username`` because
    # they are not the same thing: ``username`` is the account that signed in
    # ("admin" for the local account), whereas this identifies the *person* the
    # data belongs to. The sidebar needs the latter under the display name —
    # showing the account name there says nothing about who is on screen.
    upn: str | None = None
    # Whether this user may see organisation-wide data. Drives whether the SPA
    # offers the org view or shows it locked.
    can_view_org: bool = True
    # Whether there is an Entra identity to filter a personal view down to.
    # False for the password admin, who therefore lands on the org view.
    has_personal_view: bool = False


class AuthConfigOut(BaseModel):
    entra_enabled: bool
    redirect_uri: str
    # Build stamp, repeated here because this endpoint is reachable before
    # sign-in. Knowing which build is live is most useful exactly when you
    # cannot get in to look at the About page.
    build_date: str | None = None
    build_time: str | None = None


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
    org_view_group_id: str | None = None
    admin_group_id: str | None = None
    schedule_interval_hours: int | None = None


class AppConfigOut(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    azure_subscription_ids: list[str] = []
    cost_rolling_window_days: int = 10
    audit_backfill_days: int = 30
    report_access_group_id: str | None = None
    org_view_group_id: str | None = None
    admin_group_id: str | None = None
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


class ScanRunOut(BaseModel):
    """One row of the Scan history page.

    Both the readable label and the raw value are returned for kind and status.
    The page renders the label, but a kind this build has no label for has to
    still show something, and the raw value is the only honest fallback.
    """

    id: int
    kind: str
    raw_kind: str
    state: str
    raw_status: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: int | None = None
    error: str | None = None
    stats: dict = {}


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
    # Holds a SKU granting Copilot, with the plan still enabled. None means
    # never determined — a row that predates licence detection, or a tenant
    # whose sync has not run since.
    has_copilot_license: bool | None = None
    # Activity found for this person in the report data, so a licence that is
    # being paid for but not used is visible as a row with zeroes rather than
    # as an absence.
    cowork_events: int = 0
    total_tasks: int = 0
    last_activity_date: datetime | None = None


class UsageTrendOut(BaseModel):
    period_days: int
    active_users: int
    total_tasks: int


# --- personal view ------------------------------------------------------
# Everything below describes one person's own activity. The person is always
# taken from the caller's token, never from a request parameter.
class MySummaryOut(BaseModel):
    user_principal_name: str | None
    display_name: str | None
    report_period: int | None = None
    total_tasks: int = 0
    scheduled_tasks: int = 0
    user_initiated_tasks: int = 0
    active_days: int = 0
    last_activity_date: datetime | None = None
    cowork_events: int = 0
    credits_consumed: float = 0.0
    has_data: bool = False


class MyEventOut(BaseModel):
    event_id: str
    created_at: datetime | None
    operation: str | None
    app_host: str | None
    agent_name: str | None
    thread_id: str | None
    tools: int = 0
    accessed_resources: int = 0


class MyUsageTrendOut(BaseModel):
    period_days: int
    total_tasks: int
    scheduled_tasks: int
    user_initiated_tasks: int
    active_days: int


class MyComparisonOut(BaseModel):
    """This person's tasks against the organisation median.

    Only the aggregate is returned — never another individual's figures — so it
    stays safe to show to someone without organisation-wide access.
    """

    my_tasks: int
    org_median_tasks: int
    people_counted: int
    above_median: bool


class MyDayOut(BaseModel):
    """One day of this person's Cowork activity."""

    day: date
    sessions: int = 0
    tools: int = 0
    files: int = 0


class MyTopItemOut(BaseModel):
    """A ranked agent or tool for this person."""

    name: str | None
    value: int


class PeerStatOut(BaseModel):
    """One measure, compared against the team and the organisation.

    Only medians are carried — never another individual's figures — so the
    whole comparison stays safe to show to someone with no organisation-wide
    access.
    """

    label: str
    mine: int
    # The median across the viewer's peers — the team without them in it, so
    # the bar answers "how do I compare with the rest of my team" rather than
    # being dragged toward the viewer's own figure. Zero when withheld.
    team_median: int
    # Zero when the organisation is below the disclosure floor too. `mine` is
    # always sent: the viewer's own figures are never a disclosure.
    org_median: int
    team_people: int = 0
    org_people: int = 0


class MyStandingOut(BaseModel):
    """How this person compares, and to whom."""

    # The department this person's "team" was taken from, or the manager's name
    # when they have no department. None when the team series is not drawn.
    team_label: str | None = None
    # Why the team series is or is not there, so the page can say which. The
    # two reasons for withholding are different facts about the tenant and a
    # reader can act on one of them: "shown" | "too_small" | "unknown".
    team_state: str = "unknown"
    # Peers found in the grouping, excluding the viewer. Reported even when the
    # series is withheld, because "your team is 3 people" is the explanation.
    team_peers: int = 0
    # The floor below which a team is not drawn, so the page can name it in the
    # withholding message rather than hard-coding a number that could drift.
    min_team_peers: int = 5
    # The window all three series cover. Named on the panel, because a
    # comparison whose period is unstated invites the reader to assume it is
    # all-time for the team and recent for them.
    period_days: int = 30
    period_from: date | None = None
    period_to: date | None = None
    # The organisation series answers to the same floor as the team. The
    # arithmetic that makes a small team disclosing does not care what the
    # group is called: in a four-person pilot tenant, the organisation average
    # and the viewer's own figure narrow an individual exactly as a team of
    # four would. "shown" | "too_small" — there is no "unknown" here, because
    # the organisation is always known.
    organisation_state: str = "shown"
    # People besides the viewer. Reported even when withheld, so the page can
    # explain rather than just omit a bar.
    org_peers: int = 0
    # 0-100, measured against the organisation and never against the team: in a
    # team of four a team-relative percentile says more about the size of the
    # team than about the person.
    #
    # None when the organisation is withheld. A rank left standing after the
    # series it was measured against has gone discloses by another route.
    org_percentile: int | None = None
    org_people: int = 0
    stats: list[PeerStatOut] = []


class MyActivityOut(BaseModel):
    """Everything the personal page needs above the session list."""

    display_name: str | None = None
    user_principal_name: str | None = None
    days: int = 30
    sessions: int = 0
    tools: int = 0
    files: int = 0
    active_days: int = 0
    last_activity_date: datetime | None = None
    has_data: bool = False


# --- executive briefing -------------------------------------------------
class BriefingDeltaOut(BaseModel):
    """One measure, this period against the one before it."""

    label: str
    current: float
    previous: float
    # None when the previous period was zero: "up from nothing" has no
    # meaningful percentage, and rendering it as +100% or ∞ misleads.
    change_pct: float | None = None


class BriefingItemOut(BaseModel):
    name: str | None
    value: float
    previous: float = 0


class BriefingOut(BaseModel):
    """A deterministic executive snapshot.

    Every number here is SQL. Nothing is generated, summarised or inferred by a
    model — the page assembles its sentences from these figures against fixed
    thresholds, so it cannot invent a number in front of a customer.
    """

    window_days: int = 30
    period_start: date
    previous_start: date
    has_data: bool = False
    currency: str | None = None
    deltas: list[BriefingDeltaOut] = []
    licensed_users: int = 0
    active_licensed_users: int = 0
    idle_licensed_users: int = 0
    top_agents: list[BriefingItemOut] = []
    top_resource_groups: list[BriefingItemOut] = []
