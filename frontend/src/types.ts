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

export type MonitorType = "WEBSITE" | "API" | "HEARTBEAT" | "SSL" | "DNS" | "TCP";
export type MonitorStatus = "UP" | "DOWN" | "DEGRADED" | "PAUSED" | "MAINTENANCE" | "UNKNOWN";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD";
export type DnsRecordType = "A" | "AAAA" | "CNAME" | "MX" | "TXT" | "NS" | "SOA" | "SRV" | "PTR";

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
  environment: string | null;
  tags: string[] | null;
  port: number | null;
  record_type: DnsRecordType | null;
  expected_values: string[] | null;
  expected_headers: Record<string, string> | null;
  ssl_expiry_threshold_days: number | null;
  ssl_expires_at: string | null;
  ssl_issuer: string | null;
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

export type StatusPageService = {
  id: number;
  public_id: string;
  status_page_id: number;
  monitor_id: number;
  display_name: string;
  sort_order: number;
  is_visible: boolean;
};

export type Alert = {
  id: number;
  monitor_id: number;
  severity: "info" | "warning" | "error" | "critical";
  title: string;
  message: string;
  resolved: boolean;
  acknowledged: boolean;
  triggered_at: string;
  resolved_at: string | null;
  created_at: string;
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

export type MaintenanceWindow = {
  id: string;
  organization_id: string;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string;
  notify_subscribers: boolean;
  monitor_ids: string[];
  created_at?: string;
  updated_at?: string;
};

export type MaintenanceWindowsResponse = {
  windows: MaintenanceWindow[];
  total: number;
};

export type ApiKeyScope = "logs:write" | "metrics:write" | "traces:write";

export type ApiKey = {
  id: string;
  organization_id: string;
  name: string;
  key_prefix: string;
  scopes: ApiKeyScope[] | null;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
};

export type ApiKeyCreated = ApiKey & {
  key: string;
};

export type ApiKeysResponse = {
  api_keys: ApiKey[];
  total: number;
};

export type LogEntry = {
  id: string;
  application: string;
  environment: string | null;
  level: string;
  message: string;
  logger_name: string | null;
  host: string | null;
  trace_id: string | null;
  attributes: Record<string, unknown> | null;
  timestamp: string;
};

export type LogsResponse = {
  logs: LogEntry[];
  total: number;
};

export type LogVolumePoint = {
  bucket: string;
  total: number;
  error: number;
};

export type LogStats = {
  total: number;
  by_level: Record<string, number>;
  error_count: number;
  applications: number;
  volume: LogVolumePoint[];
  errors_by_application: Record<string, number>;
};

export type HostLatestMetrics = {
  cpu_percent: number | null;
  memory_percent: number | null;
  memory_used_mb: number | null;
  disk_percent: number | null;
  disk_used_gb: number | null;
  net_in_kb_per_s: number | null;
  net_out_kb_per_s: number | null;
  processes: number | null;
  service_checks: unknown;
  measured_at: string | null;
};

export type HostHealth = "OK" | "WARNING" | "CRITICAL" | "UNKNOWN";

export type HostEntry = {
  host: string;
  environment: string | null;
  latest: HostLatestMetrics | null;
  history: unknown[];
  threshold: Threshold | null;
  health: HostHealth;
};

export type HostsResponse = {
  hosts: HostEntry[];
  total_hosts: number;
};

export type Threshold = {
  id: string;
  organization_id: string;
  host: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  process_names: string[] | null;
  created_at?: string;
  updated_at?: string;
};

export type ThresholdsResponse = {
  thresholds: Threshold[];
  total: number;
};

export type TraceSummary = {
  trace_id: string;
  root_service: string | null;
  root_operation: string | null;
  span_count: number;
  service_count: number;
  error_count: number;
  started_at: string;
  duration_ms: number | null;
};

export type TracesResponse = {
  traces: TraceSummary[];
  total: number;
};

export type TraceSpan = {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  service: string | null;
  operation: string | null;
  kind: string | null;
  start_time: string;
  end_time: string;
  duration_ms: number | null;
  status: string | null;
  attributes: Record<string, unknown> | null;
};

export type TraceDetailResponse = {
  spans: TraceSpan[];
  total: number;
};

export type ServiceMapEdge = {
  source: string;
  target: string;
  call_count: number;
  avg_duration_ms: number | null;
  error_count: number;
};

export type ServiceMapResponse = {
  edges: ServiceMapEdge[];
  services: string[];
};

export type SLO = {
  id: string;
  organization_id: string;
  monitor_id: string;
  name: string;
  description: string | null;
  target_percentage: number;
  window_days: number;
  created_at?: string;
  updated_at?: string;
};

export type SLOsResponse = {
  slos: SLO[];
  total: number;
};

export type SLOStatus = {
  attained_percentage: number;
  target_percentage: number;
  target_met: boolean;
  error_budget_minutes: number;
  error_budget_used_minutes: number;
  error_budget_remaining_percentage: number;
  total_checks: number;
  successful_checks: number;
  monitor_name: string | null;
  period_start: string;
  period_end: string;
};

export type DashboardWidgetType =
  | "monitor_status"
  | "uptime"
  | "response_times"
  | "log_volume"
  | "host_health"
  | "incidents"
  | "service_map"
  | "slo_status";

export type DashboardWidget = {
  type: DashboardWidgetType;
  title: string;
  config: Record<string, unknown>;
};

export type DashboardTemplate = {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  widgets: DashboardWidget[];
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
};

export type DashboardsResponse = {
  dashboards: DashboardTemplate[];
  total: number;
};

export type ResponseTimesPoint = {
  bucket: string;
  avg_ms: number | null;
  p95_ms: number | null;
  count: number;
};

export type ResponseTimesResponse = {
  series: ResponseTimesPoint[];
};

export type UptimePoint = {
  bucket: string;
  uptime_percentage: number | null;
  total_checks: number;
};

export type UptimeResponse = {
  series: UptimePoint[];
};

export type ServiceHealthEntry = {
  public_id: string;
  name: string;
  monitor_type: MonitorType;
  status: MonitorStatus;
  environment: string | null;
  tags: string[] | null;
  client_name: string | null;
  in_maintenance: boolean;
  uptime_24h: number | null;
  avg_latency_24h: number | null;
  total_checks_24h: number | null;
  ssl_days_remaining: number | null;
  last_checked_at: string | null;
};

export type ServiceHealthResponse = {
  services: ServiceHealthEntry[];
  counts: {
    UP: number;
    DOWN: number;
    DEGRADED: number;
    MAINTENANCE: number;
    OTHER: number;
  };
};

export type IncidentTimelineEvent = {
  kind: "incident" | "update" | "alert" | "check" | "log" | string;
  timestamp: string;
  message: string;
};

export type IncidentTimelineResponse = {
  incident: Incident;
  events: IncidentTimelineEvent[];
};
