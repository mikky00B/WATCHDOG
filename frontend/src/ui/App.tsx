import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Bell,
  Building2,
  ChevronDown,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Gauge,
  Home,
  LogOut,
  Menu,
  MonitorCheck,
  Pencil,
  Plus,
  RadioTower,
  ShieldAlert,
  SquareChartGantt,
  Trash2,
  UserCircle,
  Users,
  X,
} from "lucide-react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  alertChannelService,
  alertService,
  authService,
  clientService,
  dashboardService,
  incidentService,
  monitorService,
  organizationService,
  reportService,
  statusPageService,
} from "../services";
import {
  apiUrl,
  clearToken,
  getRefreshToken,
  getToken,
  makeQuery,
  setRefreshToken,
  setToken,
} from "../lib/api";
import type {
  AuthResponse,
  Client,
  Monitor,
  MonitorStatus,
  MonitorType,
  MonthlyReport,
  NotificationChannel,
  Organization,
  RegisterResponse,
  StatusPage,
} from "../types";

type AuthMutationResponse = AuthResponse | RegisterResponse;

function formatDate(value: string | null | undefined) {
  if (!value) return "Not yet";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatMonth(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
  }).format(new Date(`${value}-01T00:00:00`));
}

function formatDuration(seconds: number | null | undefined) {
  const value = seconds ?? 0;
  if (value <= 0) return "0 min";
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes} min`;
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function statusClass(status: MonitorStatus | string) {
  return {
    UP: "status ok",
    DOWN: "status bad",
    DEGRADED: "status warn",
    OPEN: "status bad",
    ACKNOWLEDGED: "status warn",
    RESOLVED: "status ok",
    PAUSED: "status muted",
    MAINTENANCE: "status info",
    UNKNOWN: "status muted",
  }[status] ?? "status muted";
}

function unwrapError(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong";
}

function useAuth() {
  const query = useQuery({
    queryKey: ["me"],
    queryFn: authService.me,
    enabled: Boolean(getToken()),
  });
  return {
    user: query.data,
    isLoading: query.isLoading,
    isAuthenticated: Boolean(getToken()) && !query.isError,
  };
}

function useOrganizations() {
  const query = useQuery({
    queryKey: ["organizations"],
    queryFn: organizationService.list,
    enabled: Boolean(getToken()),
  });
  const organizations = query.data?.organizations ?? [];
  const selectedId = localStorage.getItem("watchdog_organization_public_id");
  const selected =
    organizations.find((organization) => organization.public_id === selectedId) ?? organizations[0];
  if (selected && selected.public_id !== selectedId) {
    localStorage.setItem("watchdog_organization_public_id", selected.public_id);
  }
  return { ...query, organizations, selected };
}

function LandingPage() {
  return (
    <main className="landing">
      <nav className="topbar">
        <Link className="brand" to="/">
          <ShieldAlert size={24} />
          WATCHDOG
        </Link>
        <div className="nav-actions">
          <Link to="/login">Login</Link>
          <Link className="button primary" to="/register">
            Start monitoring
          </Link>
        </div>
      </nav>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Uptime, API, and cron-job monitoring</span>
          <h1>WATCHDOG</h1>
          <p>Monitor websites, APIs, and scheduled jobs before downtime turns into client messages.</p>
          <div className="hero-actions">
            <Link className="button primary" to="/register">
              Create account
            </Link>
            <Link className="button secondary" to="/login">
              Open dashboard
            </Link>
          </div>
        </div>
        <div className="hero-panel">
          <div className="signal-row">
            <CheckCircle2 />
            <div>
              <strong>Agency API</strong>
              <span>UP · 241 ms</span>
            </div>
          </div>
          <div className="signal-row warn">
            <Clock />
            <div>
              <strong>Backup heartbeat</strong>
              <span>Next check in 14 minutes</span>
            </div>
          </div>
          <div className="signal-row bad">
            <AlertTriangle />
            <div>
              <strong>Client storefront</strong>
              <span>Incident opened · alert queued</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function AuthPage({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verificationEmail, setVerificationEmail] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [notice, setNotice] = useState("");
  const queryClient = useQueryClient();
  const mutation = useMutation<AuthMutationResponse>({
    mutationFn: async () =>
      mode === "login"
        ? authService.login({ email, password })
        : authService.register({ full_name: fullName, email, password }),
    onSuccess: (data) => {
      if ("access_token" in data) {
        setToken(data.access_token);
        setRefreshToken(data.refresh_token);
        queryClient.setQueryData(["me"], data.user);
        navigate("/app");
        return;
      }
      setVerificationEmail(data.user.email);
      setNotice(data.message);
    },
  });
  const verifyMutation = useMutation({
    mutationFn: () => authService.verifyEmail({ email: verificationEmail, code: verificationCode }),
    onSuccess: () => {
      navigate("/login");
    },
  });
  const resendMutation = useMutation({
    mutationFn: () => authService.resendVerification({ email: verificationEmail || email }),
    onSuccess: (data) => {
      setVerificationEmail(data.user.email);
      setNotice(data.message);
    },
  });

  if (mode === "register" && verificationEmail) {
    return (
      <main className="auth-shell">
        <Link className="brand" to="/">
          <ShieldAlert size={24} />
          WATCHDOG
        </Link>
        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault();
            verifyMutation.mutate();
          }}
        >
          <h1>Verify email</h1>
          {notice ? <p>{notice}</p> : null}
          <label>
            Email
            <input value={verificationEmail} readOnly />
          </label>
          <label>
            Verification code
            <input
              inputMode="numeric"
              maxLength={6}
              pattern="[0-9]{6}"
              value={verificationCode}
              onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              required
            />
          </label>
          {verifyMutation.isError ? <p className="error-text">{unwrapError(verifyMutation.error)}</p> : null}
          {resendMutation.isError ? <p className="error-text">{unwrapError(resendMutation.error)}</p> : null}
          <button className="button primary full" disabled={verificationCode.length !== 6 || verifyMutation.isPending}>
            {verifyMutation.isPending ? "Verifying..." : "Verify email"}
          </button>
          <button
            className="button secondary full"
            type="button"
            disabled={resendMutation.isPending}
            onClick={() => resendMutation.mutate()}
          >
            {resendMutation.isPending ? "Sending..." : "Resend code"}
          </button>
          <Link to="/login">Already verified?</Link>
        </form>
      </main>
    );
  }

  return (
    <main className="auth-shell">
      <Link className="brand" to="/">
        <ShieldAlert size={24} />
        WATCHDOG
      </Link>
      <form
        className="auth-form"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <h1>{mode === "login" ? "Log in" : "Create account"}</h1>
        {mode === "register" ? (
          <label>
            Full name
            <input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
          </label>
        ) : null}
        <label>
          Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            minLength={8}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {mutation.isError ? <p className="error-text">{unwrapError(mutation.error)}</p> : null}
        <button className="button primary full" disabled={mutation.isPending}>
          {mutation.isPending ? "Working..." : mode === "login" ? "Log in" : "Register"}
        </button>
        <Link to={mode === "login" ? "/register" : "/login"}>
          {mode === "login" ? "Create a new account" : "Already have an account?"}
        </Link>
        {mode === "login" ? <Link to="/forgot-password">Forgot password?</Link> : null}
      </form>
    </main>
  );
}

function PasswordResetPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const requestMutation = useMutation({
    mutationFn: () => authService.forgotPassword({ email }),
    onSuccess: () => setCodeSent(true),
  });
  const resetMutation = useMutation({
    mutationFn: () => authService.resetPassword({ email, code, new_password: newPassword }),
    onSuccess: () => navigate("/login"),
  });

  return (
    <main className="auth-shell">
      <Link className="brand" to="/">
        <ShieldAlert size={24} />
        WATCHDOG
      </Link>
      <form
        className="auth-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (codeSent) {
            resetMutation.mutate();
          } else {
            requestMutation.mutate();
          }
        }}
      >
        <h1>Reset password</h1>
        <label>
          Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        {codeSent ? (
          <>
            <label>
              Reset code
              <input
                inputMode="numeric"
                maxLength={6}
                pattern="[0-9]{6}"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                required
              />
            </label>
            <label>
              New password
              <input
                type="password"
                minLength={8}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
            </label>
          </>
        ) : null}
        {requestMutation.isError ? <p className="error-text">{unwrapError(requestMutation.error)}</p> : null}
        {resetMutation.isError ? <p className="error-text">{unwrapError(resetMutation.error)}</p> : null}
        <button className="button primary full" disabled={requestMutation.isPending || resetMutation.isPending}>
          {codeSent ? "Reset password" : "Send reset code"}
        </button>
        <Link to="/login">Back to login</Link>
      </form>
    </main>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

function Shell() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { organizations, selected } = useOrganizations();
  const [isMobileNavOpen, setMobileNavOpen] = useState(false);
  const [isAccountMenuOpen, setAccountMenuOpen] = useState(false);
  const navItems = [
    { to: "/app", label: "Overview", icon: Home },
    { to: "/app/monitors", label: "Monitors", icon: MonitorCheck },
    { to: "/app/alerts", label: "Alerts", icon: Bell },
    { to: "/app/incidents", label: "Incidents", icon: AlertTriangle },
    { to: "/app/clients", label: "Clients", icon: Users },
    { to: "/app/alert-channels", label: "Alert Channels", icon: Bell },
    { to: "/app/status-pages", label: "Status Pages", icon: RadioTower },
    { to: "/app/reports", label: "Reports", icon: SquareChartGantt },
  ];

  useEffect(() => {
    setMobileNavOpen(false);
    setAccountMenuOpen(false);
  }, [location.pathname]);

  async function logout() {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      await authService.logout({ refresh_token: refreshToken }).catch(() => undefined);
    }
    clearToken();
    queryClient.clear();
    navigate("/login");
  }

  return (
    <div className={isMobileNavOpen ? "app-shell nav-open" : "app-shell"}>
      <button
        className="nav-backdrop"
        aria-label="Close navigation"
        onClick={() => setMobileNavOpen(false)}
      />
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar-head">
          <Link className="brand" to="/app">
            <ShieldAlert size={24} />
            WATCHDOG
          </Link>
          <button
            className="icon-button sidebar-close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileNavOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <nav className="side-nav">
          {navItems.map((item) => (
            <Link
              key={item.to}
              className={
                item.to === "/app"
                  ? location.pathname === item.to
                    ? "active"
                    : undefined
                  : location.pathname.startsWith(item.to)
                    ? "active"
                    : undefined
              }
              to={item.to}
            >
              <item.icon size={18} />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="workspace">
        <header className="workspace-header">
          <button
            className="icon-button mobile-menu-button"
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu size={19} />
          </button>
          <div className="workspace-selector">
            <span className="eyebrow">Workspace</span>
            <select
              value={selected?.public_id ?? ""}
              onChange={(event) => {
                localStorage.setItem("watchdog_organization_public_id", event.target.value);
                queryClient.invalidateQueries();
              }}
            >
              {organizations.map((organization) => (
                <option key={organization.public_id} value={organization.public_id}>
                  {organization.name}
                </option>
              ))}
            </select>
          </div>
          <div className="header-actions">
            <Link className="button secondary" to="/app/organizations/new">
              <Building2 size={16} />
              Organization
            </Link>
            <div className="account-menu">
              <button
                className="account-button"
                type="button"
                aria-haspopup="menu"
                aria-expanded={isAccountMenuOpen}
                onClick={() => setAccountMenuOpen((open) => !open)}
              >
                <UserCircle size={18} />
                <span>{user?.full_name ?? "Account"}</span>
                <ChevronDown size={15} />
              </button>
              {isAccountMenuOpen ? (
                <div className="account-popover" role="menu">
                  <strong>{user?.full_name ?? "Account"}</strong>
                  <button type="button" role="menuitem" onClick={logout}>
                    <LogOut size={16} />
                    Log out
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={selected ? <Overview organization={selected} /> : <EmptyOrganizations />} />
            <Route path="/organizations/new" element={<CreateOrganization />} />
            <Route path="/monitors" element={<MonitorList organization={selected} />} />
            <Route path="/monitors/new" element={<CreateMonitor organization={selected} />} />
            <Route path="/monitors/:monitorId" element={<MonitorDetail />} />
            <Route path="/alerts" element={<Alerts organization={selected} />} />
            <Route path="/incidents" element={<IncidentList organization={selected} />} />
            <Route path="/incidents/:incidentId" element={<IncidentDetail />} />
            <Route path="/clients" element={<Clients organization={selected} />} />
            <Route path="/alert-channels" element={<AlertChannels organization={selected} />} />
            <Route path="/status-pages" element={<StatusPages organization={selected} />} />
            <Route path="/reports" element={<Reports organization={selected} />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function EmptyOrganizations() {
  return (
    <section className="empty-state">
      <Building2 size={36} />
      <h1>Create your first organization</h1>
      <p>Organizations scope monitors, incidents, and alert channels.</p>
      <Link className="button primary" to="/app/organizations/new">
        Create organization
      </Link>
    </section>
  );
}

function CreateOrganization() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const mutation = useMutation({
    mutationFn: () => organizationService.create({ name, slug: slug || slugify(name) }),
    onSuccess: (organization) => {
      localStorage.setItem("watchdog_organization_public_id", organization.public_id);
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      navigate("/app");
    },
  });

  return (
    <section>
      <PageHeader title="New organization" description="Create the workspace that owns your monitors." />
      <form
        className="form-panel"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <label>
          Organization name
          <input
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setSlug(slugify(event.target.value));
            }}
            required
          />
        </label>
        <label>
          Slug
          <input value={slug} onChange={(event) => setSlug(slugify(event.target.value))} required />
        </label>
        {mutation.isError ? <p className="error-text">{unwrapError(mutation.error)}</p> : null}
        <button className="button primary">Create organization</button>
      </form>
    </section>
  );
}

function Overview({ organization }: { organization: Organization }) {
  const stats = useQuery({
    queryKey: ["stats", organization.public_id],
    queryFn: () => dashboardService.stats(organization.public_id),
  });
  const monitors = useQuery({
    queryKey: ["monitors", organization.public_id],
    queryFn: () => monitorService.list(organization.public_id),
  });
  const incidents = useQuery({
    queryKey: ["incidents", organization.public_id],
    queryFn: () => incidentService.list(organization.public_id),
  });
  const data = stats.data;
  const failedRate = data?.total_checks ? Math.round((data.failed_checks / data.total_checks) * 100) : 0;
  const chartData = useMemo(
    () =>
      (monitors.data?.monitors ?? []).slice(0, 8).map((monitor, index) => ({
        name: monitor.name,
        checks: Math.max(1, monitor.consecutive_successes + monitor.consecutive_failures + index),
      })),
    [monitors.data],
  );

  return (
    <section>
      <PageHeader title="Overview" description="Current health across monitors, incidents, and alerts." />
      {stats.isLoading ? <SkeletonGrid /> : null}
      {stats.isError ? <ErrorBox message={unwrapError(stats.error)} /> : null}
      {data ? (
        <>
          <div className="metric-grid">
            <Metric label="Total monitors" value={data.total_monitors} icon={MonitorCheck} />
            <Metric label="Enabled monitors" value={data.enabled_monitors} icon={CheckCircle2} />
            <Metric label="Failed checks" value={data.failed_checks} icon={AlertTriangle} tone="bad" />
            <Metric label="Failure rate" value={`${failedRate}%`} icon={Gauge} tone={failedRate ? "warn" : "ok"} />
            <Metric label="Active alerts" value={data.active_alerts} icon={Bell} tone="warn" />
            <Metric label="Heartbeats" value={data.total_heartbeats} icon={RadioTower} />
          </div>
          <div className="two-column">
            <section className="panel">
              <h2>Monitor activity</h2>
              {chartData.length ? (
                <div className="bar-chart">
                  {chartData.map((item) => (
                    <div key={item.name} className="bar-row">
                      <span>{item.name}</span>
                      <div>
                        <i style={{ width: `${Math.min(100, item.checks * 14)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyInline text="No monitor activity yet." />
              )}
            </section>
            <section className="panel">
              <h2>Recent incidents</h2>
              {(incidents.data?.incidents ?? []).length ? (
                <div className="list-stack">
                  {incidents.data!.incidents.slice(0, 5).map((incident) => (
                    <Link key={incident.id} to={`/app/incidents/${incident.id}`} className="list-row">
                      <strong>{incident.title}</strong>
                      <span className={statusClass(incident.status)}>{incident.status}</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <EmptyInline text="No incidents recorded." />
              )}
            </section>
          </div>
        </>
      ) : null}
    </section>
  );
}

function MonitorList({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  if (!organization) {
    return <EmptyOrganizations />;
  }

  const query = useQuery({
    queryKey: ["monitors", organization?.public_id],
    queryFn: () => monitorService.list(organization.public_id),
  });
  const remove = useMutation({
    mutationFn: (id: string) => monitorService.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["monitors"] }),
  });
  const monitors = query.data?.monitors ?? [];

  return (
    <section>
      <PageHeader title="Monitors" description="Websites, APIs, and heartbeat jobs in this workspace.">
        <Link className="button primary" to="/app/monitors/new">
          <Plus size={16} />
          New monitor
        </Link>
      </PageHeader>
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {remove.isError ? <ErrorBox message={unwrapError(remove.error)} /> : null}
      {!query.isLoading && !monitors.length ? <EmptyInline text="No monitors yet." /> : null}
      {monitors.length ? (
        <DataTable
          headers={["Name", "Type", "Target", "Status", "Last checked", ""]}
          rows={monitors.map((monitor) => [
            <Link to={`/app/monitors/${monitor.public_id}`}>{monitor.name}</Link>,
            monitor.monitor_type,
            monitor.heartbeat_url ?? monitor.url ?? "Heartbeat",
            <span className={statusClass(monitor.status)}>{monitor.status}</span>,
            formatDate(monitor.last_checked_at),
            <div className="row-actions">
              <Link className="button compact" to={`/app/monitors/${monitor.public_id}`}>
                View
              </Link>
              <button
                className="icon-button"
                title="Delete monitor"
                disabled={remove.isPending}
                onClick={() => {
                  if (confirm(`Delete monitor "${monitor.name}"?`)) {
                    remove.mutate(monitor.public_id);
                  }
                }}
              >
                <Trash2 size={16} />
              </button>
            </div>,
          ])}
        />
      ) : null}
    </section>
  );
}

function CreateMonitor({ organization }: { organization?: Organization }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [type, setType] = useState<MonitorType>("WEBSITE");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("GET");
  const [interval, setIntervalValue] = useState(300);
  const [expectedStatus, setExpectedStatus] = useState(200);
  const [expectedText, setExpectedText] = useState("");
  const [requestBody, setRequestBody] = useState("");
  const [clientId, setClientId] = useState("");
  const clients = useQuery({
    queryKey: ["clients", organization?.public_id],
    queryFn: () => clientService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const [created, setCreated] = useState<Monitor | null>(null);
  const mutation = useMutation({
    mutationFn: () => {
      if (!organization) {
        throw new Error("Create an organization before adding monitors.");
      }
      return (
      monitorService.create({
        organization_id: organization.public_id,
        client_id: clientId || null,
        name,
        monitor_type: type,
        url: type === "HEARTBEAT" ? null : url,
        http_method: method,
        expected_status_code: type === "HEARTBEAT" ? null : expectedStatus,
        expected_response_text: expectedText || null,
        request_body: requestBody || null,
        interval_seconds: interval,
        timeout_seconds: 5,
        enabled: true,
      })
      );
    },
    onSuccess: (monitor) => {
      setCreated(monitor);
      queryClient.invalidateQueries({ queryKey: ["monitors", organization?.public_id] });
      if (monitor.monitor_type !== "HEARTBEAT") {
        navigate("/app/monitors");
      }
    },
  });

  if (!organization) {
    return <EmptyOrganizations />;
  }

  return (
    <section>
      <PageHeader
        title="New monitor"
        description={`Create a website, API, or heartbeat monitor in ${organization.name}.`}
      />
      <form
        className="form-panel wide"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <div className="segmented">
          {(["WEBSITE", "API", "HEARTBEAT"] as MonitorType[]).map((option) => (
            <button
              type="button"
              key={option}
              className={type === option ? "active" : ""}
              onClick={() => setType(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          Client
          <select value={clientId} onChange={(event) => setClientId(event.target.value)}>
            <option value="">No client</option>
            {(clients.data?.clients ?? []).map((client) => (
              <option key={client.public_id} value={client.public_id}>
                {client.name}
              </option>
            ))}
          </select>
        </label>
        {type !== "HEARTBEAT" ? (
          <label>
            Target URL
            <input type="url" value={url} onChange={(event) => setUrl(event.target.value)} required />
          </label>
        ) : null}
        <div className="form-grid">
          <label>
            Method
            <select value={method} onChange={(event) => setMethod(event.target.value)}>
              {["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"].map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
          <label>
            Interval seconds
            <input
              type="number"
              min={10}
              max={3600}
              value={interval}
              onChange={(event) => setIntervalValue(Number(event.target.value))}
            />
          </label>
          {type !== "HEARTBEAT" ? (
            <label>
              Expected status
              <input
                type="number"
                min={100}
                max={599}
                value={expectedStatus}
                onChange={(event) => setExpectedStatus(Number(event.target.value))}
              />
            </label>
          ) : null}
        </div>
        {type === "API" ? (
          <>
            <label>
              Expected response text
              <input value={expectedText} onChange={(event) => setExpectedText(event.target.value)} />
            </label>
            <label>
              Request body
              <textarea value={requestBody} onChange={(event) => setRequestBody(event.target.value)} />
            </label>
          </>
        ) : null}
        {mutation.isError ? <p className="error-text">{unwrapError(mutation.error)}</p> : null}
        <button className="button primary">Create monitor</button>
      </form>
      {created?.heartbeat_url ? (
        <section className="panel success-panel">
          <h2>Heartbeat URL</h2>
          <code>{`${location.origin.replace("5173", "8000")}${created.heartbeat_url}`}</code>
          <button
            className="button secondary"
            onClick={() =>
              navigator.clipboard.writeText(`${location.origin.replace("5173", "8000")}${created.heartbeat_url}`)
            }
          >
            <Copy size={16} />
            Copy
          </button>
        </section>
      ) : null}
    </section>
  );
}

function MonitorDetail() {
  const { monitorId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["monitor", monitorId],
    queryFn: () => monitorService.get(monitorId),
  });
  const stats = useQuery({
    queryKey: ["monitor-stats", monitorId],
    queryFn: () => monitorService.stats(monitorId),
  });
  const checks = useQuery({
    queryKey: ["monitor-checks", monitorId],
    queryFn: () => monitorService.checks(monitorId),
  });
  const refreshMonitor = () => {
    queryClient.invalidateQueries({ queryKey: ["monitor", monitorId] });
    queryClient.invalidateQueries({ queryKey: ["monitor-stats", monitorId] });
    queryClient.invalidateQueries({ queryKey: ["monitor-checks", monitorId] });
    queryClient.invalidateQueries({ queryKey: ["monitors"] });
  };
  const pause = useMutation({
    mutationFn: () => monitorService.pause(monitorId),
    onSuccess: refreshMonitor,
  });
  const resume = useMutation({
    mutationFn: () => monitorService.resume(monitorId),
    onSuccess: refreshMonitor,
  });
  const runCheck = useMutation({
    mutationFn: () => monitorService.runCheck(monitorId),
    onSuccess: refreshMonitor,
  });
  const monitor = query.data;
  const [editName, setEditName] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editInterval, setEditInterval] = useState(60);
  const [editExpectedStatus, setEditExpectedStatus] = useState<number | "">("");
  const [editThreshold, setEditThreshold] = useState<number | "">("");

  useEffect(() => {
    if (!monitor) return;
    setEditName(monitor.name);
    setEditUrl(monitor.url ?? "");
    setEditInterval(monitor.interval_seconds);
    setEditExpectedStatus(monitor.expected_status_code ?? "");
    setEditThreshold(monitor.response_time_threshold_ms ?? "");
  }, [monitor]);

  const update = useMutation({
    mutationFn: () =>
      monitorService.update(monitorId, {
        name: editName,
        url: monitor?.monitor_type === "HEARTBEAT" ? undefined : editUrl || null,
        interval_seconds: editInterval,
        expected_status_code: editExpectedStatus === "" ? null : editExpectedStatus,
        response_time_threshold_ms: editThreshold === "" ? null : editThreshold,
      }),
    onSuccess: refreshMonitor,
  });
  const remove = useMutation({
    mutationFn: () => monitorService.remove(monitorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["monitors"] });
      navigate("/app/monitors");
    },
  });

  return (
    <section>
      {query.isLoading ? <SkeletonGrid /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {monitor ? (
        <>
          <PageHeader title={monitor.name} description={monitor.url ?? monitor.heartbeat_url ?? "Heartbeat monitor"}>
            <button
              className="button secondary"
              disabled={pause.isPending || resume.isPending}
              onClick={() => (monitor.enabled ? pause.mutate() : resume.mutate())}
            >
              {monitor.enabled ? "Pause" : "Resume"}
            </button>
            <button className="button primary" disabled={runCheck.isPending} onClick={() => runCheck.mutate()}>
              Run check
            </button>
            <button
              className="button secondary"
              disabled={remove.isPending}
              onClick={() => {
                if (confirm(`Delete monitor "${monitor.name}"?`)) {
                  remove.mutate();
                }
              }}
            >
              <Trash2 size={16} />
              Delete
            </button>
          </PageHeader>
          {pause.isError ? <ErrorBox message={unwrapError(pause.error)} /> : null}
          {resume.isError ? <ErrorBox message={unwrapError(resume.error)} /> : null}
          {runCheck.isError ? <ErrorBox message={unwrapError(runCheck.error)} /> : null}
          {update.isError ? <ErrorBox message={unwrapError(update.error)} /> : null}
          {remove.isError ? <ErrorBox message={unwrapError(remove.error)} /> : null}
          <div className="metric-grid">
            <Metric label="Status" value={monitor.status} icon={Activity} />
            <Metric label="Type" value={monitor.monitor_type} icon={MonitorCheck} />
            <Metric label="Failures" value={monitor.consecutive_failures} icon={AlertTriangle} tone="bad" />
            <Metric label="Successes" value={monitor.consecutive_successes} icon={CheckCircle2} tone="ok" />
            <Metric
              label="Uptime"
              value={stats.data ? `${stats.data.uptime_percentage}%` : "0%"}
              icon={Gauge}
              tone="ok"
            />
            <Metric
              label="Avg latency"
              value={stats.data?.average_latency_ms ? `${stats.data.average_latency_ms} ms` : "No data"}
              icon={Clock}
            />
          </div>
          <div className="two-column">
            <section className="panel">
              <h2>Configuration</h2>
              <dl className="details-grid">
                <dt>Method</dt>
                <dd>{monitor.http_method}</dd>
                <dt>Expected status</dt>
                <dd>{monitor.expected_status_code ?? "Any"}</dd>
                <dt>Interval</dt>
                <dd>{monitor.interval_seconds}s</dd>
                <dt>Last checked</dt>
                <dd>{formatDate(monitor.last_checked_at)}</dd>
                <dt>Next check</dt>
                <dd>{formatDate(monitor.next_check_at)}</dd>
              </dl>
            </section>
            <form
              className="panel edit-panel"
              onSubmit={(event) => {
                event.preventDefault();
                update.mutate();
              }}
            >
              <h2>Edit monitor</h2>
              <label>
                Name
                <input value={editName} onChange={(event) => setEditName(event.target.value)} required />
              </label>
              {monitor.monitor_type !== "HEARTBEAT" ? (
                <label>
                  Target URL
                  <input type="url" value={editUrl} onChange={(event) => setEditUrl(event.target.value)} required />
                </label>
              ) : null}
              <div className="form-grid compact-grid">
                <label>
                  Interval seconds
                  <input
                    type="number"
                    min={10}
                    max={3600}
                    value={editInterval}
                    onChange={(event) => setEditInterval(Number(event.target.value))}
                  />
                </label>
                <label>
                  Expected status
                  <input
                    type="number"
                    min={100}
                    max={599}
                    value={editExpectedStatus}
                    onChange={(event) =>
                      setEditExpectedStatus(event.target.value ? Number(event.target.value) : "")
                    }
                    disabled={monitor.monitor_type === "HEARTBEAT"}
                  />
                </label>
                <label>
                  Latency threshold
                  <input
                    type="number"
                    min={1}
                    value={editThreshold}
                    onChange={(event) => setEditThreshold(event.target.value ? Number(event.target.value) : "")}
                  />
                </label>
              </div>
              <button className="button primary" disabled={update.isPending}>
                {update.isPending ? "Saving..." : "Save changes"}
              </button>
            </form>
            <section className="panel">
              <h2>Recent checks</h2>
              {checks.isLoading ? <div className="skeleton table-skeleton" /> : null}
              {checks.isError ? <ErrorBox message={unwrapError(checks.error)} /> : null}
              {!checks.isLoading && !(checks.data?.results.length ?? 0) ? (
                <EmptyInline text="No check results yet." />
              ) : null}
              {checks.data?.results.length ? (
                <div className="list-stack">
                  {checks.data.results.slice(0, 8).map((check) => (
                    <div key={check.id} className="list-row">
                      <strong>{formatDate(check.checked_at)}</strong>
                      <span>{check.latency_ms ? `${Math.round(check.latency_ms)} ms` : "No latency"}</span>
                      <span className={check.success ? "status ok" : "status bad"}>
                        {check.success ? "PASS" : "FAIL"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          </div>
        </>
      ) : null}
    </section>
  );
}

function Alerts({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["alerts", organization?.public_id],
    queryFn: () => alertService.list(organization?.public_id),
    enabled: Boolean(organization),
  });
  const acknowledge = useMutation({
    mutationFn: (id: number) => alertService.acknowledge(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const resolve = useMutation({
    mutationFn: (id: number) => alertService.resolve(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const alerts = query.data?.alerts ?? [];

  if (!organization) {
    return <EmptyOrganizations />;
  }

  return (
    <section>
      <PageHeader title="Alerts" description="Triggered monitor alerts that need attention." />
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {acknowledge.isError ? <ErrorBox message={unwrapError(acknowledge.error)} /> : null}
      {resolve.isError ? <ErrorBox message={unwrapError(resolve.error)} /> : null}
      {!query.isLoading && !alerts.length ? <EmptyInline text="No alerts recorded." /> : null}
      {alerts.length ? (
        <DataTable
          headers={["Alert", "Severity", "Status", "Monitor", "Created", "Message", ""]}
          rows={alerts.map((alert) => [
            alert.title,
            alert.severity,
            <span className={alert.resolved ? "status ok" : alert.acknowledged ? "status warn" : "status bad"}>
              {alert.resolved ? "RESOLVED" : alert.acknowledged ? "ACKNOWLEDGED" : "OPEN"}
            </span>,
            `Monitor #${alert.monitor_id}`,
            formatDate(alert.created_at || alert.triggered_at),
            alert.message,
            <div className="row-actions">
              <button
                className="button compact"
                disabled={alert.acknowledged || alert.resolved || acknowledge.isPending}
                onClick={() => acknowledge.mutate(alert.id)}
              >
                Acknowledge
              </button>
              <button
                className="button compact"
                disabled={alert.resolved || resolve.isPending}
                onClick={() => resolve.mutate(alert.id)}
              >
                Resolve
              </button>
            </div>,
          ])}
        />
      ) : null}
    </section>
  );
}

function IncidentList({ organization }: { organization?: Organization }) {
  const query = useQuery({
    queryKey: ["incidents", organization?.public_id],
    queryFn: () => incidentService.list(organization?.public_id),
    enabled: Boolean(organization),
  });
  const incidents = query.data?.incidents ?? [];
  return (
    <section>
      <PageHeader title="Incidents" description="Open and resolved outage records." />
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {!query.isLoading && !incidents.length ? <EmptyInline text="No incidents recorded." /> : null}
      {incidents.length ? (
        <DataTable
          headers={["Title", "Severity", "Status", "Started", "Duration", ""]}
          rows={incidents.map((incident) => [
            <Link to={`/app/incidents/${incident.id}`}>{incident.title}</Link>,
            incident.severity,
            <span className={statusClass(incident.status)}>{incident.status}</span>,
            formatDate(incident.started_at),
            incident.duration_seconds ? `${Math.round(incident.duration_seconds / 60)} min` : "Ongoing",
            <Link className="button compact" to={`/app/incidents/${incident.id}`}>
              View
            </Link>,
          ])}
        />
      ) : null}
    </section>
  );
}

function IncidentDetail() {
  const { incidentId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => incidentService.get(incidentId),
  });
  const acknowledge = useMutation({
    mutationFn: () => incidentService.acknowledge(incidentId, "Acknowledged from dashboard"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["incident", incidentId] }),
  });
  const resolve = useMutation({
    mutationFn: () => incidentService.resolve(incidentId, "Resolved from dashboard"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["incident", incidentId] }),
  });
  const incident = query.data;

  return (
    <section>
      {query.isLoading ? <SkeletonGrid /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {incident ? (
        <>
          <PageHeader title={incident.title} description={incident.reason}>
            <button className="button secondary" onClick={() => acknowledge.mutate()}>
              Acknowledge
            </button>
            <button className="button primary" onClick={() => resolve.mutate()}>
              Resolve
            </button>
          </PageHeader>
          <div className="metric-grid">
            <Metric label="Status" value={incident.status} icon={AlertTriangle} />
            <Metric label="Severity" value={incident.severity} icon={Gauge} />
            <Metric label="Started" value={formatDate(incident.started_at)} icon={Clock} />
            <Metric label="Resolved" value={formatDate(incident.resolved_at)} icon={CheckCircle2} tone="ok" />
          </div>
        </>
      ) : null}
    </section>
  );
}

function AlertChannels({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["alert-channels", organization?.id],
    queryFn: () => alertChannelService.list(organization?.id),
    enabled: Boolean(organization),
  });
  const [name, setName] = useState("");
  const [type, setType] = useState<NotificationChannel["channel_type"]>("EMAIL");
  const [target, setTarget] = useState("");
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [editName, setEditName] = useState("");
  const [editTarget, setEditTarget] = useState("");
  const [editActive, setEditActive] = useState(true);
  const create = useMutation({
    mutationFn: () =>
      alertChannelService.create({
        organization_id: organization?.id,
        name,
        channel_type: type,
        config: type === "EMAIL" ? { email: target } : { chat_id: target },
      }),
    onSuccess: () => {
      setName("");
      setTarget("");
      queryClient.invalidateQueries({ queryKey: ["alert-channels"] });
    },
  });
  const update = useMutation({
    mutationFn: () =>
      alertChannelService.update(editing!.id, {
        name: editName,
        config: editing!.channel_type === "EMAIL" ? { email: editTarget } : { chat_id: editTarget },
        is_active: editActive,
      }),
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["alert-channels"] });
    },
  });
  const channels = query.data?.channels ?? [];

  return (
    <section>
      <PageHeader title="Alert Channels" description="Email and Telegram destinations for incident alerts." />
      <form
        className="form-panel inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <input placeholder="Channel name" value={name} onChange={(event) => setName(event.target.value)} required />
        <select value={type} onChange={(event) => setType(event.target.value as NotificationChannel["channel_type"])}>
          <option>EMAIL</option>
          <option>TELEGRAM</option>
        </select>
        <input
          placeholder={type === "EMAIL" ? "alerts@example.com" : "Telegram chat ID"}
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          required
        />
        <button className="button primary">Create</button>
      </form>
      {create.isError ? <ErrorBox message={unwrapError(create.error)} /> : null}
      {update.isError ? <ErrorBox message={unwrapError(update.error)} /> : null}
      {editing ? (
        <form
          className="form-panel inline-form edit-strip"
          onSubmit={(event) => {
            event.preventDefault();
            update.mutate();
          }}
        >
          <input value={editName} onChange={(event) => setEditName(event.target.value)} required />
          <input value={editTarget} onChange={(event) => setEditTarget(event.target.value)} required />
          <label className="check-label">
            <input type="checkbox" checked={editActive} onChange={(event) => setEditActive(event.target.checked)} />
            Active
          </label>
          <div className="row-actions">
            <button className="button primary" disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save"}
            </button>
            <button className="button secondary" type="button" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}
      {query.isLoading ? <TableSkeleton /> : null}
      {!query.isLoading && !channels.length ? <EmptyInline text="No alert channels yet." /> : null}
      {channels.length ? (
        <DataTable
          headers={["Name", "Type", "Target", "Status", ""]}
          rows={channels.map((channel) => [
            channel.name,
            channel.channel_type,
            String(channel.config.email ?? channel.config.chat_id ?? "Configured"),
            channel.is_active ? <span className="status ok">ACTIVE</span> : <span className="status muted">OFF</span>,
            <ChannelActions
              channel={channel}
              onEdit={() => {
                setEditing(channel);
                setEditName(channel.name);
                setEditTarget(String(channel.config.email ?? channel.config.chat_id ?? ""));
                setEditActive(channel.is_active);
              }}
            />,
          ])}
        />
      ) : null}
    </section>
  );
}

function Clients({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [editing, setEditing] = useState<Client | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const query = useQuery({
    queryKey: ["clients", organization?.public_id],
    queryFn: () => clientService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const create = useMutation({
    mutationFn: () =>
      clientService.create(organization!.public_id, {
        name,
        contact_email: email || null,
        notes: notes || null,
      }),
    onSuccess: () => {
      setName("");
      setEmail("");
      setNotes("");
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });
  const update = useMutation({
    mutationFn: () =>
      clientService.update(organization!.public_id, editing!.public_id, {
        name: editName,
        contact_email: editEmail || null,
        notes: editNotes || null,
      }),
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });
  const remove = useMutation({
    mutationFn: (clientId: string) => clientService.remove(organization!.public_id, clientId),
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });
  const clients = query.data?.clients ?? [];

  return (
    <section>
      <PageHeader title="Clients" description="Group monitors by client or project." />
      <form
        className="form-panel inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <input placeholder="Client name" value={name} onChange={(event) => setName(event.target.value)} required />
        <input type="email" placeholder="Contact email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <input placeholder="Notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
        <button className="button primary">Create</button>
      </form>
      {create.isError ? <ErrorBox message={unwrapError(create.error)} /> : null}
      {update.isError ? <ErrorBox message={unwrapError(update.error)} /> : null}
      {remove.isError ? <ErrorBox message={unwrapError(remove.error)} /> : null}
      {editing ? (
        <form
          className="form-panel inline-form edit-strip"
          onSubmit={(event) => {
            event.preventDefault();
            update.mutate();
          }}
        >
          <input value={editName} onChange={(event) => setEditName(event.target.value)} required />
          <input type="email" value={editEmail} onChange={(event) => setEditEmail(event.target.value)} />
          <input value={editNotes} onChange={(event) => setEditNotes(event.target.value)} />
          <div className="row-actions">
            <button className="button primary" disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save"}
            </button>
            <button className="button secondary" type="button" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}
      {query.isLoading ? <TableSkeleton /> : null}
      {!query.isLoading && !clients.length ? <EmptyInline text="No clients yet." /> : null}
      {clients.length ? (
        <DataTable
          headers={["Name", "Contact", "Notes", "Created", ""]}
          rows={clients.map((client) => [
            client.name,
            client.contact_email ?? "No contact",
            client.notes ?? "",
            formatDate(client.created_at),
            <div className="row-actions">
              <button
                className="icon-button"
                title="Edit client"
                onClick={() => {
                  setEditing(client);
                  setEditName(client.name);
                  setEditEmail(client.contact_email ?? "");
                  setEditNotes(client.notes ?? "");
                }}
              >
                <Pencil size={16} />
              </button>
              <button
                className="icon-button"
                title="Delete client"
                disabled={remove.isPending}
                onClick={() => {
                  if (confirm(`Delete client "${client.name}"?`)) {
                    remove.mutate(client.public_id);
                  }
                }}
              >
                <Trash2 size={16} />
              </button>
            </div>,
          ])}
        />
      ) : null}
    </section>
  );
}

function StatusPages({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [editing, setEditing] = useState<StatusPage | null>(null);
  const [editName, setEditName] = useState("");
  const [editSlug, setEditSlug] = useState("");
  const [editActive, setEditActive] = useState(true);
  const pages = useQuery({
    queryKey: ["status-pages", organization?.public_id],
    queryFn: () => statusPageService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const monitors = useQuery({
    queryKey: ["monitors", organization?.public_id],
    queryFn: () => monitorService.list(organization?.public_id),
    enabled: Boolean(organization),
  });
  const create = useMutation({
    mutationFn: () =>
      statusPageService.create({
        organization_id: organization!.public_id,
        name,
        slug: slug || slugify(name),
        brand_color: "#2563eb",
      }),
    onSuccess: () => {
      setName("");
      setSlug("");
      queryClient.invalidateQueries({ queryKey: ["status-pages"] });
    },
  });
  const update = useMutation({
    mutationFn: () =>
      statusPageService.update(editing!.public_id, {
        name: editName,
        slug: editSlug,
        is_active: editActive,
      }),
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["status-pages"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => statusPageService.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["status-pages"] }),
  });
  const statusPages = pages.data?.status_pages ?? [];

  return (
    <section>
      <PageHeader title="Status Pages" description="Publish selected monitor status for clients." />
      <form
        className="form-panel inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <input
          placeholder="Page name"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setSlug(slugify(event.target.value));
          }}
          required
        />
        <input placeholder="slug" value={slug} onChange={(event) => setSlug(slugify(event.target.value))} required />
        <button className="button primary">Create</button>
      </form>
      {create.isError ? <ErrorBox message={unwrapError(create.error)} /> : null}
      {update.isError ? <ErrorBox message={unwrapError(update.error)} /> : null}
      {remove.isError ? <ErrorBox message={unwrapError(remove.error)} /> : null}
      {editing ? (
        <form
          className="form-panel inline-form edit-strip"
          onSubmit={(event) => {
            event.preventDefault();
            update.mutate();
          }}
        >
          <input value={editName} onChange={(event) => setEditName(event.target.value)} required />
          <input value={editSlug} onChange={(event) => setEditSlug(slugify(event.target.value))} required />
          <label className="check-label">
            <input type="checkbox" checked={editActive} onChange={(event) => setEditActive(event.target.checked)} />
            Active
          </label>
          <div className="row-actions">
            <button className="button primary" disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save"}
            </button>
            <button className="button secondary" type="button" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}
      {pages.isLoading ? <TableSkeleton /> : null}
      {!pages.isLoading && !statusPages.length ? <EmptyInline text="No status pages yet." /> : null}
      {statusPages.length ? (
        <>
          <DataTable
            headers={["Name", "Slug", "Status", "Public URL", ""]}
            rows={statusPages.map((page) => {
              const publicPath = `/status/${page.slug}`;
              const publicUrl = `${location.origin}${publicPath}`;
              return [
                page.name,
                page.slug,
                page.is_active ? <span className="status ok">ACTIVE</span> : <span className="status muted">OFF</span>,
                <Link className="truncate-link" to={publicPath}>{publicPath}</Link>,
                <div className="row-actions">
                  <button
                    className="icon-button"
                    title="Copy public link"
                    onClick={() => navigator.clipboard.writeText(publicUrl)}
                  >
                    <Copy size={16} />
                  </button>
                  <Link className="icon-button" title="Open public page" to={publicPath} target="_blank">
                    <ExternalLink size={16} />
                  </Link>
                  <button
                    className="icon-button"
                    title="Edit status page"
                    onClick={() => {
                      setEditing(page);
                      setEditName(page.name);
                      setEditSlug(page.slug);
                      setEditActive(page.is_active);
                    }}
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    className="icon-button"
                    title="Delete status page"
                    disabled={remove.isPending}
                    onClick={() => {
                      if (confirm(`Delete status page "${page.name}"?`)) {
                        remove.mutate(page.public_id);
                      }
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>,
              ];
            })}
          />
          <div className="management-grid">
            {statusPages.map((page) => (
              <StatusPageServices
                key={page.public_id}
                page={page}
                monitors={monitors.data?.monitors ?? []}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}

function StatusPageServices({ page, monitors }: { page: StatusPage; monitors: Monitor[] }) {
  const queryClient = useQueryClient();
  const [monitorId, setMonitorId] = useState("");
  const services = useQuery({
    queryKey: ["status-page-services", page.public_id],
    queryFn: () => statusPageService.services(page.public_id),
  });
  const addService = useMutation({
    mutationFn: () =>
      statusPageService.addService(page.public_id, {
        monitor_id: monitorId,
        display_name: monitors.find((monitor) => monitor.public_id === monitorId)?.name ?? "Service",
      }),
    onSuccess: () => {
      setMonitorId("");
      queryClient.invalidateQueries({ queryKey: ["status-page-services", page.public_id] });
      queryClient.invalidateQueries({ queryKey: ["public-status-page", page.slug] });
    },
  });
  const removeService = useMutation({
    mutationFn: (serviceId: string) => statusPageService.removeService(page.public_id, serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["status-page-services", page.public_id] });
      queryClient.invalidateQueries({ queryKey: ["public-status-page", page.slug] });
    },
  });
  const attached = services.data?.services ?? [];

  return (
    <section className="panel service-manager">
      <h2>{page.name}</h2>
      <form
        className="inline-controls"
        onSubmit={(event) => {
          event.preventDefault();
          addService.mutate();
        }}
      >
        <select value={monitorId} onChange={(event) => setMonitorId(event.target.value)} required>
          <option value="">Select monitor</option>
          {monitors.map((monitor) => (
            <option key={monitor.public_id} value={monitor.public_id}>
              {monitor.name}
            </option>
          ))}
        </select>
        <button className="button primary" disabled={!monitorId || addService.isPending}>
          {addService.isPending ? "Adding..." : "Add service"}
        </button>
      </form>
      {services.isLoading ? <div className="skeleton table-skeleton" /> : null}
      {services.isError ? <ErrorBox message={unwrapError(services.error)} /> : null}
      {addService.isError ? <ErrorBox message={unwrapError(addService.error)} /> : null}
      {removeService.isError ? <ErrorBox message={unwrapError(removeService.error)} /> : null}
      {!services.isLoading && !attached.length ? (
        <EmptyInline text="No services are attached to this status page." />
      ) : null}
      {attached.length ? (
        <div className="list-stack">
          {attached.map((service) => (
            <div className="list-row" key={service.public_id}>
              <strong>{service.display_name}</strong>
              <span>{service.is_visible ? "Visible" : "Hidden"}</span>
              <button
                className="icon-button"
                title="Remove service"
                disabled={removeService.isPending}
                onClick={() => {
                  if (confirm(`Remove "${service.display_name}" from ${page.name}?`)) {
                    removeService.mutate(service.public_id);
                  }
                }}
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function Reports({ organization }: { organization?: Organization }) {
  const now = new Date();
  const defaultMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const [monthValue, setMonthValue] = useState(defaultMonth);
  const [clientId, setClientId] = useState("");
  const [htmlError, setHtmlError] = useState("");
  const [year, month] = monthValue.split("-").map(Number);
  const clients = useQuery({
    queryKey: ["clients", organization?.public_id],
    queryFn: () => clientService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const report = useQuery({
    queryKey: ["monthly-report", organization?.public_id, clientId, year, month],
    queryFn: () =>
      reportService.monthly({
        organizationId: organization!.public_id,
        clientId: clientId || undefined,
        year,
        month,
      }),
    enabled: false,
  });
  const data = report.data as MonthlyReport | undefined;

  async function openHtmlReport() {
    if (!organization) return;
    setHtmlError("");
    const token = getToken();
    const response = await fetch(
      apiUrl(
        `/reports/monthly/html${makeQuery({
          organization_id: organization.public_id,
          client_id: clientId,
          year,
          month,
        })}`,
      ),
      { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
    );
    if (!response.ok) {
      setHtmlError("HTML report could not be opened.");
      return;
    }
    const blob = await response.blob();
    window.open(URL.createObjectURL(blob), "_blank", "noopener,noreferrer");
  }

  if (!organization) {
    return <EmptyOrganizations />;
  }

  return (
    <section>
      <PageHeader title="Reports" description="Monthly reliability summaries for clients and workspaces.">
        <button className="button secondary" onClick={openHtmlReport} disabled={!data}>
          Open HTML
        </button>
      </PageHeader>
      <div className="form-panel inline-form">
        <select value={clientId} onChange={(event) => setClientId(event.target.value)}>
          <option value="">All clients</option>
          {(clients.data?.clients ?? []).map((client) => (
            <option key={client.public_id} value={client.public_id}>
              {client.name}
            </option>
          ))}
        </select>
        <input type="month" value={monthValue} onChange={(event) => setMonthValue(event.target.value)} />
        <button
          className="button primary"
          onClick={() => {
            setHtmlError("");
            report.refetch();
          }}
          disabled={!organization || !year || !month || report.isFetching}
        >
          {report.isFetching ? "Generating..." : "Generate report"}
        </button>
      </div>
      {report.isFetching ? <SkeletonGrid /> : null}
      {report.isError ? <ErrorBox message={unwrapError(report.error)} /> : null}
      {htmlError ? <ErrorBox message={htmlError} /> : null}
      {data ? (
        <>
          <div className="report-title">
            <span className="eyebrow">{formatMonth(monthValue)}</span>
            <h2>{data.client_name}</h2>
          </div>
          <div className="metric-grid">
            <Metric label="Uptime" value={`${data.uptime_percentage}%`} icon={Gauge} tone="ok" />
            <Metric label="Downtime" value={formatDuration(data.total_downtime_seconds)} icon={Clock} />
            <Metric label="Incidents" value={data.incident_count} icon={AlertTriangle} tone="warn" />
            <Metric
              label="Avg response"
              value={data.average_response_time_ms != null ? `${data.average_response_time_ms} ms` : "No data"}
              icon={Activity}
            />
            <Metric label="Monitors" value={data.monitors_included} icon={MonitorCheck} />
          </div>
          <section className="panel">
            <h2>Monitors included</h2>
            {data.monitors.length ? (
              <DataTable
                headers={["Name", "Type", "Status", "Checks", "Uptime", "Downtime", "Avg response"]}
                rows={data.monitors.map((monitor) => [
                  monitor.name,
                  monitor.monitor_type,
                  <span className={statusClass(monitor.status)}>{monitor.status}</span>,
                  `${monitor.successful_checks}/${monitor.total_checks}`,
                  `${monitor.uptime_percentage}%`,
                  formatDuration(monitor.downtime_seconds),
                  monitor.average_response_time_ms != null ? `${monitor.average_response_time_ms} ms` : "No data",
                ])}
              />
            ) : (
              <EmptyInline text="No monitors match this report scope." />
            )}
          </section>
          <section className="panel">
            <h2>Incident list</h2>
            {data.incidents.length ? (
              <DataTable
                headers={["Incident", "Monitor", "Severity", "Status", "Started", "Duration"]}
                rows={data.incidents.map((incident) => [
                  incident.title,
                  incident.monitor_name,
                  incident.severity,
                  <span className={statusClass(incident.status)}>{incident.status}</span>,
                  formatDate(incident.started_at),
                  formatDuration(incident.duration_seconds),
                ])}
              />
            ) : (
              <EmptyInline text="No incidents in this period." />
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}

function PublicStatusPage() {
  const { slug = "" } = useParams();
  const query = useQuery({
    queryKey: ["public-status-page", slug],
    queryFn: () => statusPageService.public(slug),
  });
  const page = query.data;

  return (
    <main className="public-status">
      {query.isLoading ? <SkeletonGrid /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {page ? (
        <section className="public-status-inner">
          <header className="page-header">
            <div>
              <span className="eyebrow">Public status</span>
              <h1>{page.name}</h1>
              <p>Last updated {formatDate(new Date().toISOString())}</p>
            </div>
            <span className={page.overall_status === "OPERATIONAL" ? "status ok" : "status bad"}>
              {page.overall_status}
            </span>
          </header>
          <section className="panel">
            <h2>Services</h2>
            {page.services.length ? (
              <div className="list-stack">
                {page.services.map((service) => (
                  <div className="list-row" key={service.id}>
                    <strong>{service.display_name}</strong>
                    <span>{service.uptime_30d}% uptime</span>
                    <span className={statusClass(service.status)}>{service.status}</span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyInline text="No public services are configured." />
            )}
          </section>
        </section>
      ) : null}
    </main>
  );
}

function ChannelActions({ channel, onEdit }: { channel: NotificationChannel; onEdit: () => void }) {
  const queryClient = useQueryClient();
  const test = useMutation({ mutationFn: () => alertChannelService.test(channel.id) });
  const remove = useMutation({
    mutationFn: () => alertChannelService.remove(channel.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alert-channels"] }),
  });
  return (
    <div className="row-actions">
      <button className="icon-button" title="Send test alert" onClick={() => test.mutate()}>
        <Bell size={16} />
      </button>
      <button className="icon-button" title="Edit channel" onClick={onEdit}>
        <Pencil size={16} />
      </button>
      <button
        className="icon-button"
        title="Delete channel"
        disabled={remove.isPending}
        onClick={() => {
          if (confirm(`Delete alert channel "${channel.name}"?`)) {
            remove.mutate();
          }
        }}
      >
        <Trash2 size={16} />
      </button>
    </div>
  );
}

function Placeholder({ title }: { title: string }) {
  return (
    <section className="empty-state">
      <SquareChartGantt size={36} />
      <h1>{title}</h1>
      <p>This UI section is reserved for the next backend milestone.</p>
    </section>
  );
}

function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children ? <div className="page-actions">{children}</div> : null}
    </header>
  );
}

function Metric({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  icon: typeof Activity;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <section className={`metric ${tone ?? ""}`}>
      <Icon size={20} />
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: React.ReactNode[][] }) {
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {headers.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>
                    <span className="cell-value">{cell}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mobile-card-list">
        {rows.map((row, index) => (
          <section className="mobile-card" key={index}>
            {row.map((cell, cellIndex) => {
              const header = headers[cellIndex];
              const isActions = !header;
              return (
                <div className={isActions ? "mobile-card-actions" : "mobile-card-row"} key={cellIndex}>
                  {isActions ? null : <span>{header}</span>}
                  <strong>{cell}</strong>
                </div>
              );
            })}
          </section>
        ))}
      </div>
    </>
  );
}

function ErrorBox({ message }: { message: string }) {
  return <div className="error-box">{message}</div>;
}

function EmptyInline({ text }: { text: string }) {
  return <div className="empty-inline">{text}</div>;
}

function SkeletonGrid() {
  return (
    <div className="metric-grid">
      {Array.from({ length: 4 }).map((_, index) => (
        <div className="skeleton" key={index} />
      ))}
    </div>
  );
}

function TableSkeleton() {
  return <div className="skeleton table-skeleton" />;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/status/:slug" element={<PublicStatusPage />} />
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/forgot-password" element={<PasswordResetPage />} />
      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <Shell />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
