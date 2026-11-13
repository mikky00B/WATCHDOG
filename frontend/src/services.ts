import { apiRequest, makeQuery } from "./lib/api";
import type {
  Alert,
  ApiKey,
  ApiKeyCreated,
  ApiKeysResponse,
  ApiKeyScope,
  AuthResponse,
  CheckResult,
  Client,
  DashboardStats,
  DashboardTemplate,
  DashboardsResponse,
  HostsResponse,
  Incident,
  IncidentTimelineResponse,
  ListResponse,
  LogStats,
  LogsResponse,
  MaintenanceWindow,
  MaintenanceWindowsResponse,
  Monitor,
  MonitorStats,
  MonthlyReport,
  NotificationChannel,
  Organization,
  PublicStatusPage,
  RegisterResponse,
  ResponseTimesResponse,
  SLO,
  SLOStatus,
  SLOsResponse,
  ServiceHealthResponse,
  ServiceMapResponse,
  StatusPage,
  StatusPageService,
  Threshold,
  ThresholdsResponse,
  TraceDetailResponse,
  TracesResponse,
  UptimeResponse,
  User,
} from "./types";

export const authService = {
  register(payload: { full_name: string; email: string; password: string }) {
    return apiRequest<RegisterResponse>("/auth/register", { method: "POST", body: payload, auth: false });
  },
  login(payload: { email: string; password: string }) {
    return apiRequest<AuthResponse>("/auth/login", { method: "POST", body: payload, auth: false });
  },
  verifyEmail(payload: { email: string; code: string }) {
    return apiRequest<User>("/auth/verify-email", { method: "POST", body: payload, auth: false });
  },
  resendVerification(payload: { email: string }) {
    return apiRequest<RegisterResponse>("/auth/resend-verification", {
      method: "POST",
      body: payload,
      auth: false,
    });
  },
  forgotPassword(payload: { email: string }) {
    return apiRequest<{ message: string }>("/auth/forgot-password", {
      method: "POST",
      body: payload,
      auth: false,
    });
  },
  resetPassword(payload: { email: string; code: string; new_password: string }) {
    return apiRequest<User>("/auth/reset-password", { method: "POST", body: payload, auth: false });
  },
  refresh(payload: { refresh_token: string }) {
    return apiRequest<AuthResponse>("/auth/refresh", { method: "POST", body: payload, auth: false });
  },
  logout(payload: { refresh_token: string }) {
    return apiRequest<{ message: string }>("/auth/logout", { method: "POST", body: payload, auth: false });
  },
  me() {
    return apiRequest<User>("/auth/me");
  },
};

export const organizationService = {
  create(payload: { name: string; slug: string }) {
    return apiRequest<Organization>("/organizations/", { method: "POST", body: payload });
  },
  list() {
    return apiRequest<ListResponse<Organization, "organizations">>("/organizations/");
  },
};

export const dashboardService = {
  stats(organizationId?: string) {
    return apiRequest<DashboardStats>(`/stats${makeQuery({ organization_id: organizationId })}`);
  },
};

export const monitorService = {
  list(
    organizationId?: string,
    filters?: {
      monitor_type?: string;
      status?: string;
      environment?: string;
      tag?: string;
    },
  ) {
    return apiRequest<ListResponse<Monitor, "monitors">>(
      `/monitors/${makeQuery({
        organization_id: organizationId,
        monitor_type: filters?.monitor_type,
        status: filters?.status,
        environment: filters?.environment,
        tag: filters?.tag,
      })}`,
    );
  },
  get(id: string) {
    return apiRequest<Monitor>(`/monitors/${id}`);
  },
  create(payload: Record<string, unknown>) {
    return apiRequest<Monitor>("/monitors/", { method: "POST", body: payload });
  },
  update(id: string, payload: Record<string, unknown>) {
    return apiRequest<Monitor>(`/monitors/${id}`, { method: "PATCH", body: payload });
  },
  pause(id: string) {
    return apiRequest<Monitor>(`/monitors/${id}/pause`, { method: "POST" });
  },
  resume(id: string) {
    return apiRequest<Monitor>(`/monitors/${id}/resume`, { method: "POST" });
  },
  runCheck(id: string) {
    return apiRequest<CheckResult>(`/monitors/${id}/run-check`, { method: "POST" });
  },
  checks(id: string) {
    return apiRequest<ListResponse<CheckResult, "results">>(`/monitors/${id}/checks`);
  },
  stats(id: string) {
    return apiRequest<MonitorStats>(`/monitors/${id}/stats`);
  },
  remove(id: string) {
    return apiRequest<void>(`/monitors/${id}`, { method: "DELETE" });
  },
};

export const clientService = {
  list(organizationId: string) {
    return apiRequest<ListResponse<Client, "clients">>(`/organizations/${organizationId}/clients`);
  },
  create(organizationId: string, payload: Record<string, unknown>) {
    return apiRequest<Client>(`/organizations/${organizationId}/clients`, {
      method: "POST",
      body: payload,
    });
  },
  update(organizationId: string, id: string, payload: Record<string, unknown>) {
    return apiRequest<Client>(`/organizations/${organizationId}/clients/${id}`, {
      method: "PATCH",
      body: payload,
    });
  },
  remove(organizationId: string, id: string) {
    return apiRequest<void>(`/organizations/${organizationId}/clients/${id}`, { method: "DELETE" });
  },
};

export const alertService = {
  list(organizationId?: string, unresolvedOnly?: boolean) {
    return apiRequest<ListResponse<Alert, "alerts">>(
      `/alerts/${makeQuery({ organization_id: organizationId, unresolved_only: unresolvedOnly })}`,
    );
  },
  acknowledge(id: number) {
    return apiRequest<Alert>(`/alerts/${id}/acknowledge`, { method: "POST" });
  },
  resolve(id: number) {
    return apiRequest<Alert>(`/alerts/${id}/resolve`, { method: "POST" });
  },
};

export const incidentService = {
  list(organizationId?: string, status?: string) {
    return apiRequest<ListResponse<Incident, "incidents">>(
      `/incidents/${makeQuery({ organization_id: organizationId, status })}`,
    );
  },
  get(id: string) {
    return apiRequest<Incident>(`/incidents/${id}`);
  },
  acknowledge(id: string, note?: string) {
    return apiRequest<Incident>(`/incidents/${id}/acknowledge${makeQuery({ note })}`, {
      method: "POST",
    });
  },
  resolve(id: string, note?: string) {
    return apiRequest<Incident>(`/incidents/${id}/resolve${makeQuery({ note })}`, {
      method: "POST",
    });
  },
};

export const alertChannelService = {
  list(organizationInternalId?: number) {
    return apiRequest<ListResponse<NotificationChannel, "channels">>(
      `/alert-channels/${makeQuery({ organization_id: organizationInternalId })}`,
    );
  },
  create(payload: Record<string, unknown>) {
    return apiRequest<NotificationChannel>("/alert-channels/", { method: "POST", body: payload });
  },
  update(id: number, payload: Record<string, unknown>) {
    return apiRequest<NotificationChannel>(`/alert-channels/${id}`, { method: "PATCH", body: payload });
  },
  test(id: number) {
    return apiRequest<unknown>(`/alert-channels/${id}/test`, { method: "POST" });
  },
  remove(id: number) {
    return apiRequest<void>(`/alert-channels/${id}`, { method: "DELETE" });
  },
};

export const statusPageService = {
  list(organizationId: string) {
    return apiRequest<ListResponse<StatusPage, "status_pages">>(
      `/status-pages/${makeQuery({ organization_id: organizationId })}`,
    );
  },
  create(payload: Record<string, unknown>) {
    return apiRequest<StatusPage>("/status-pages/", { method: "POST", body: payload });
  },
  update(id: string, payload: Record<string, unknown>) {
    return apiRequest<StatusPage>(`/status-pages/${id}`, { method: "PATCH", body: payload });
  },
  remove(id: string) {
    return apiRequest<void>(`/status-pages/${id}`, { method: "DELETE" });
  },
  services(id: string) {
    return apiRequest<ListResponse<StatusPageService, "services">>(`/status-pages/${id}/services`);
  },
  addService(statusPageId: string, payload: Record<string, unknown>) {
    return apiRequest<unknown>(`/status-pages/${statusPageId}/services`, {
      method: "POST",
      body: payload,
    });
  },
  removeService(statusPageId: string, serviceId: string) {
    return apiRequest<void>(`/status-pages/${statusPageId}/services/${serviceId}`, { method: "DELETE" });
  },
  public(slug: string) {
    return apiRequest<PublicStatusPage>(`/public/status-pages/${slug}`, { auth: false });
  },
};

export const reportService = {
  monthly(params: { organizationId: string; clientId?: string; year: number; month: number }) {
    return apiRequest<MonthlyReport>(
      `/reports/monthly${makeQuery({
        organization_id: params.organizationId,
        client_id: params.clientId,
        year: params.year,
        month: params.month,
      })}`,
    );
  },
};

export const maintenanceWindowService = {
  list(organizationId: string) {
    return apiRequest<MaintenanceWindowsResponse>(
      `/maintenance-windows/${makeQuery({ organization_id: organizationId })}`,
    );
  },
  get(id: string) {
    return apiRequest<MaintenanceWindow>(`/maintenance-windows/${id}`);
  },
  create(payload: Record<string, unknown>) {
    return apiRequest<MaintenanceWindow>("/maintenance-windows/", { method: "POST", body: payload });
  },
  update(id: string, payload: Record<string, unknown>) {
    return apiRequest<MaintenanceWindow>(`/maintenance-windows/${id}`, { method: "PATCH", body: payload });
  },
  remove(id: string) {
    return apiRequest<void>(`/maintenance-windows/${id}`, { method: "DELETE" });
  },
};

export const apiKeyService = {
  list(organizationId: string) {
    return apiRequest<ApiKeysResponse>(`/api-keys/${makeQuery({ organization_id: organizationId })}`);
  },
  create(payload: {
    organization_id: string;
    name: string;
    expires_at?: string | null;
    scopes?: ApiKeyScope[];
  }) {
    return apiRequest<ApiKeyCreated>("/api-keys/", { method: "POST", body: payload });
  },
  remove(id: string) {
    return apiRequest<ApiKey>(`/api-keys/${id}`, { method: "DELETE" });
  },
};

export const logService = {
  list(params: {
    organizationId: string;
    application?: string;
    level?: string;
    environment?: string;
    search?: string;
    traceId?: string;
    limit?: number;
  }) {
    return apiRequest<LogsResponse>(
      `/logs/${makeQuery({
        organization_id: params.organizationId,
        application: params.application,
        level: params.level,
        environment: params.environment,
        search: params.search,
        trace_id: params.traceId,
        limit: params.limit,
      })}`,
    );
  },
  stats(organizationId: string, period?: string) {
    return apiRequest<LogStats>(`/logs/stats${makeQuery({ organization_id: organizationId, period })}`);
  },
};

export const infrastructureService = {
  hosts(organizationId: string, historyHours?: number) {
    return apiRequest<HostsResponse>(
      `/infrastructure/hosts${makeQuery({ organization_id: organizationId, history_hours: historyHours })}`,
    );
  },
  thresholds(organizationId: string) {
    return apiRequest<ThresholdsResponse>(
      `/infrastructure/thresholds${makeQuery({ organization_id: organizationId })}`,
    );
  },
  createThreshold(payload: Record<string, unknown>) {
    return apiRequest<Threshold>("/infrastructure/thresholds", { method: "POST", body: payload });
  },
  updateThreshold(id: string, payload: Record<string, unknown>) {
    return apiRequest<Threshold>(`/infrastructure/thresholds/${id}`, { method: "PATCH", body: payload });
  },
  removeThreshold(id: string) {
    return apiRequest<void>(`/infrastructure/thresholds/${id}`, { method: "DELETE" });
  },
};

export const traceService = {
  list(params: { organizationId: string; service?: string; period?: string; limit?: number }) {
    return apiRequest<TracesResponse>(
      `/traces/${makeQuery({
        organization_id: params.organizationId,
        service: params.service,
        period: params.period,
        limit: params.limit,
      })}`,
    );
  },
  get(traceId: string, organizationId: string) {
    return apiRequest<TraceDetailResponse>(`/traces/${traceId}${makeQuery({ organization_id: organizationId })}`);
  },
  serviceMap(organizationId: string, period?: string) {
    return apiRequest<ServiceMapResponse>(
      `/traces/service-map${makeQuery({ organization_id: organizationId, period })}`,
    );
  },
};

export const sloService = {
  list(organizationId: string) {
    return apiRequest<SLOsResponse>(`/slos/${makeQuery({ organization_id: organizationId })}`);
  },
  get(id: string) {
    return apiRequest<SLO>(`/slos/${id}`);
  },
  status(id: string) {
    return apiRequest<SLOStatus>(`/slos/${id}/status`);
  },
  create(payload: Record<string, unknown>) {
    return apiRequest<SLO>("/slos/", { method: "POST", body: payload });
  },
  update(id: string, payload: Record<string, unknown>) {
    return apiRequest<SLO>(`/slos/${id}`, { method: "PATCH", body: payload });
  },
  remove(id: string) {
    return apiRequest<void>(`/slos/${id}`, { method: "DELETE" });
  },
};

export const dashboardTemplateService = {
  list(organizationId: string) {
    return apiRequest<DashboardsResponse>(`/dashboards/${makeQuery({ organization_id: organizationId })}`);
  },
  create(payload: Record<string, unknown>) {
    return apiRequest<DashboardTemplate>("/dashboards/", { method: "POST", body: payload });
  },
  update(id: string, payload: Record<string, unknown>) {
    return apiRequest<DashboardTemplate>(`/dashboards/${id}`, { method: "PATCH", body: payload });
  },
  remove(id: string) {
    return apiRequest<void>(`/dashboards/${id}`, { method: "DELETE" });
  },
};

export const analyticsService = {
  responseTimes(params: { organizationId: string; period?: string; monitorId?: string; clientId?: string }) {
    return apiRequest<ResponseTimesResponse>(
      `/analytics/response-times${makeQuery({
        organization_id: params.organizationId,
        period: params.period,
        monitor_id: params.monitorId,
        client_id: params.clientId,
      })}`,
    );
  },
  uptime(params: { organizationId: string; period?: string }) {
    return apiRequest<UptimeResponse>(
      `/analytics/uptime${makeQuery({ organization_id: params.organizationId, period: params.period })}`,
    );
  },
  serviceHealth(organizationId: string) {
    return apiRequest<ServiceHealthResponse>(
      `/analytics/service-health${makeQuery({ organization_id: organizationId })}`,
    );
  },
  infrastructure(organizationId: string, historyHours?: number) {
    return apiRequest<HostsResponse>(
      `/analytics/infrastructure${makeQuery({ organization_id: organizationId, history_hours: historyHours })}`,
    );
  },
  incidentTimeline(incidentId: string | number) {
    return apiRequest<IncidentTimelineResponse>(`/analytics/incidents/${incidentId}/timeline`);
  },
};
