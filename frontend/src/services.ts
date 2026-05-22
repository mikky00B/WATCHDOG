import { apiRequest, makeQuery } from "./lib/api";
import type {
  AuthResponse,
  CheckResult,
  Client,
  DashboardStats,
  Incident,
  ListResponse,
  Monitor,
  MonitorStats,
  MonthlyReport,
  NotificationChannel,
  Organization,
  PublicStatusPage,
  RegisterResponse,
  StatusPage,
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
  list(organizationId?: string) {
    return apiRequest<ListResponse<Monitor, "monitors">>(
      `/monitors/${makeQuery({ organization_id: organizationId })}`,
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
  addService(statusPageId: string, payload: Record<string, unknown>) {
    return apiRequest<unknown>(`/status-pages/${statusPageId}/services`, {
      method: "POST",
      body: payload,
    });
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
