// Shared API response types (mirror api/schemas.py).

export interface User {
  username: string;
  role: string;
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
  total_tasks: number;
  scheduled_tasks: number;
  user_initiated_tasks: number;
  active_days: number;
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
