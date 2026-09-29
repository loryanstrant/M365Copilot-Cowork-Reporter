// Shared API response types (mirror api/schemas.py).

export interface User {
  username: string;
  role: string;
  /** Entra display name. Null for the password admin, and for tokens issued
   *  before display names were carried, so always fall back to the username. */
  display_name: string | null;
  /** The signed-in person's UPN — not the same as `username`, which is the
   *  account that signed in ("admin" for the local account). */
  upn: string | null;
  /** May see organisation-wide data (admin, or in the org-view group). */
  can_view_org: boolean;
  /** Has an Entra identity to filter a personal view to. False for the
   *  password admin, who therefore lands on the organisation view. */
  has_personal_view: boolean;
}

/** One person's own Cowork activity — always the signed-in caller's. */
export interface MySummary {
  user_principal_name: string | null;
  display_name: string | null;
  report_period: number | null;
  total_tasks: number;
  scheduled_tasks: number;
  user_initiated_tasks: number;
  active_days: number;
  last_activity_date: string | null;
  cowork_events: number;
  credits_consumed: number;
  has_data: boolean;
}

export interface MyEvent {
  event_id: string;
  created_at: string | null;
  operation: string | null;
  app_host: string | null;
  agent_name: string | null;
  thread_id: string | null;
  tools: number;
  accessed_resources: number;
}

export interface MyComparison {
  my_tasks: number;
  org_median_tasks: number;
  people_counted: number;
  above_median: boolean;
}

export interface Kpis {
  total_cost: number;
  currency: string | null;
  total_credits: number;
  total_tasks: number;
  active_users: number;
  cowork_events: number;
}

export interface CostByGroup {
  resource_group: string | null;
  cost_centre: string | null;
  project: string | null;
  cost: number;
}

export interface CostTrend {
  cost_date: string;
  cost: number;
}

export interface UsageByUser {
  user_principal_name: string;
  display_name: string | null;
  department: string | null;
  job_title: string | null;
  company_name: string | null;
  office_location: string | null;
  country: string | null;
  manager_name: string | null;
  total_tasks: number;
  scheduled_tasks: number;
  user_initiated_tasks: number;
  active_days: number;
  last_activity_date: string | null;
}

export interface DirectoryUser {
  user_principal_name: string | null;
  display_name: string | null;
  job_title: string | null;
  department: string | null;
  company_name: string | null;
  office_location: string | null;
  city: string | null;
  country: string | null;
  manager_name: string | null;
  user_type: string | null;
  account_enabled: boolean | null;
  /** Holds a Copilot-granting SKU with the plan enabled. Null = undetermined. */
  has_copilot_license: boolean | null;
  cowork_events: number;
  total_tasks: number;
  last_activity_date: string | null;
}

export interface UsageTrend {
  period_days: number;
  active_users: number;
  total_tasks: number;
}

export interface AppConfig {
  tenant_id: string | null;
  client_id: string | null;
  has_client_secret: boolean;
  azure_subscription_ids: string[];
  cost_rolling_window_days: number;
  audit_backfill_days: number;
  report_access_group_id: string | null;
  /** Members may see organisation-wide data. Null = open to all signed-in users. */
  org_view_group_id: string | null;
  /** Members get admin on Entra sign-in. Null = nobody does (fails closed). */
  admin_group_id: string | null;
  schedule_interval_hours: number;
  configured: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface TestConnection {
  ok: boolean;
  graph_token: boolean;
  arm_token: boolean;
  directory_read: boolean;
  audit_query: boolean;
  cost_read: boolean;
  directory_users: number | null;
  detail: string | null;
}

export interface Status {
  configured: boolean;
  last_run: {
    id: number;
    job_name: string;
    status: string;
    started_at: string | null;
    finished_at: string | null;
    stats: Record<string, unknown> | null;
  } | null;
  cowork_events: number;
  daily_cost_rows: number;
  cowork_usage_rows: number;
  credit_rows: number;
  directory_users: number;
}

export interface BillingPolicy {
  resource_group: string;
  billing_policy_name: string | null;
  cost_centre: string | null;
  business_owner: string | null;
  project: string | null;
  notes: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface UploadResult {
  rows: number;
  imported: number;
  skipped: number;
  detail: string | null;
}

export interface MyActivity {
  display_name: string | null;
  user_principal_name: string | null;
  days: number;
  sessions: number;
  tools: number;
  files: number;
  active_days: number;
  last_activity_date: string | null;
  has_data: boolean;
}

export interface MyDay {
  day: string;
  sessions: number;
  tools: number;
  files: number;
}

export interface MyTopItem {
  name: string | null;
  value: number;
}

export interface PeerStat {
  label: string;
  mine: number;
  team_median: number;
  org_median: number;
  team_people: number;
  org_people: number;
}

export interface MyStanding {
  /** Department, or the manager's name, or null when neither is known. */
  team_label: string | null;
  org_percentile: number;
  stats: PeerStat[];
}

export interface BriefingDelta {
  label: string;
  current: number;
  previous: number;
  /** Null when the previous period was zero — there is no honest percentage. */
  change_pct: number | null;
}

export interface BriefingItem {
  name: string | null;
  value: number;
  previous: number;
}

export interface Briefing {
  window_days: number;
  period_start: string;
  previous_start: string;
  has_data: boolean;
  currency: string | null;
  deltas: BriefingDelta[];
  licensed_users: number;
  active_licensed_users: number;
  idle_licensed_users: number;
  top_agents: BriefingItem[];
  top_resource_groups: BriefingItem[];
}
