export type User = {
  id: number;
  public_id: string;
  full_name: string;
  email: string;
  is_verified: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AuthResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: User;
};

export type RegisterResponse = {
  user: User;
  message: string;
};

export type Organization = {
  id: number;
  public_id: string;
  name: string;
  slug: string;
  owner_id: number;
  created_at: string;
  updated_at: string;
};

export type MonitorType = "WEBSITE" | "API" | "HEARTBEAT" | "SSL";
export type MonitorStatus = "UP" | "DOWN" | "DEGRADED" | "PAUSED" | "MAINTENANCE" | "UNKNOWN";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD";

export type Monitor = {
  id: number;
  public_id: string;
  name: string;
  url: string | null;
  monitor_type: MonitorType;
  http_method: HttpMethod;
  expected_status_code: number | null;
  expected_response_text: string | null;
  expected_json: Record<string, unknown> | null;
  request_headers: Record<string, string> | null;
  request_body: string | null;
  interval_seconds: number;
  timeout_seconds: number;
  response_time_threshold_ms: number | null;
  enabled: boolean;
  heartbeat_key: string | null;
  heartbeat_url: string | null;
  status: MonitorStatus;
  consecutive_failures: number;
  consecutive_successes: number;
  last_checked_at: string | null;
  next_check_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Incident = {
  id: number;
  organization_id: number | null;
  monitor_id: number;
  title: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED" | "IGNORED";
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  reason: string;
  started_at: string;
  acknowledged_at: string | null;
  acknowledged_by: number | null;
  resolved_at: string | null;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string;
};

export type NotificationChannel = {
  id: number;
  organization_id: number | null;
  name: string;
  channel_type: "EMAIL" | "TELEGRAM";
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Client = {
  id: number;
  public_id: string;
  organization_id: number;
  name: string;
  contact_email: string | null;
  logo_url: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type StatusPage = {
  id: number;
  public_id: string;
  organization_id: number;
  name: string;
  slug: string;
  logo_url: string | null;
  brand_color: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type PublicStatusPage = {
  name: string;
  slug: string;
  logo_url: string | null;
  brand_color: string | null;
  overall_status: "OPERATIONAL" | "DEGRADED" | "MAJOR_OUTAGE" | "MAINTENANCE";
  services: {
    id: number;
    display_name: string;
    status: MonitorStatus;
    uptime_30d: number;
  }[];
  active_incidents: Record<string, unknown>[];
  recent_incidents: Record<string, unknown>[];
  maintenance_windows: Record<string, unknown>[];
};

export type DashboardStats = {
  total_monitors: number;
  enabled_monitors: number;
  total_checks: number;
  failed_checks: number;
  active_alerts: number;
  total_heartbeats: number;
};

export type CheckResult = {
  id: number;
  monitor_id: number;
  status_code: number | null;
  latency_ms: number | null;
  success: boolean;
  error_message: string | null;
  checked_at: string;
};

export type MonitorStats = {
  monitor_id: number;
  total_checks: number;
  successful_checks: number;
  failed_checks: number;
  uptime_percentage: number;
  average_latency_ms: number | null;
  last_checked_at: string | null;
  last_status_code: number | null;
  last_error_message: string | null;
};

export type MonthlyReport = {
  organization_id: string;
  organization_name: string;
  client_id: string | null;
  client_name: string;
  period_start: string;
  period_end: string;
  monitors_included: number;
  uptime_percentage: number;
  total_downtime_seconds: number;
  incident_count: number;
  average_response_time_ms: number | null;
  monitors: {
    monitor_id: string;
    name: string;
    monitor_type: MonitorType;
    status: MonitorStatus;
    total_checks: number;
    successful_checks: number;
    failed_checks: number;
    uptime_percentage: number;
    downtime_seconds: number;
    incident_count: number;
    average_response_time_ms: number | null;
  }[];
  incidents: {
    id: number;
    monitor_id: string;
    monitor_name: string;
    title: string;
    status: Incident["status"];
    severity: Incident["severity"];
    started_at: string;
    resolved_at: string | null;
    duration_seconds: number | null;
  }[];
};

export type ListResponse<T, K extends string> = Record<K, T[]> & {
  total: number;
};
