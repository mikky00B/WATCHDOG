import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
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
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  MonitorCheck,
  Network,
  Pencil,
  Plus,
  RadioTower,
  ScrollText,
  Server,
  ShieldCheck,
  SquareChartGantt,
  Target,
  Trash2,
  UserCircle,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { LogoMark } from "./LogoMark";
import {
  alertChannelService,
  alertService,
  analyticsService,
  checkService,
  apiKeyService,
  authService,
  clientService,
  dashboardService,
  dashboardTemplateService,
  incidentService,
  infrastructureService,
  logService,
  maintenanceWindowService,
  monitorService,
  organizationService,
  reportService,
  sloService,
  statusPageService,
  traceService,
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
  ApiKey,
  ApiKeyCreated,
  ApiKeyScope,
  AuthResponse,
  Client,
  DashboardTemplate,
  DnsRecordType,
  LogEntry,
  MaintenanceWindow,
  Monitor,
  MonitorStatus,
  MonitorType,
  MonthlyReport,
  NotificationChannel,
  Organization,
  RegisterResponse,
  SLO,
  ServiceMapEdge,
  StatusPage,
  Threshold,
  TraceSpan,
} from "../types";

type AuthMutationResponse = AuthResponse | RegisterResponse;
type ToastTone = "success" | "info" | "error";
type ToastMessage = {
  id: number;
  tone: ToastTone;
  message: string;
};
type Notify = (message: string, tone?: ToastTone) => void;

const NotificationContext = createContext<Notify>(() => undefined);

function useNotify() {
  return useContext(NotificationContext);
}

type ConfirmOptions = {
  title: string;
  message?: string;
  confirmLabel?: string;
};

const ConfirmContext = createContext<(options: ConfirmOptions) => Promise<boolean>>(async () => false);

function useConfirm() {
  return useContext(ConfirmContext);
}

function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const confirmAction = useCallback((next: ConfirmOptions) => {
    setOptions(next);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const close = useCallback((value: boolean) => {
    setOptions(null);
    resolverRef.current?.(value);
    resolverRef.current = null;
  }, []);

  return (
    <ConfirmContext.Provider value={confirmAction}>
      {children}
      {options ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title">
            <h2 id="confirm-modal-title">{options.title}</h2>
            {options.message ? <p>{options.message}</p> : null}
            <div className="modal-actions">
              <button className="button secondary" type="button" onClick={() => close(false)}>
                Cancel
              </button>
              <button className="button danger" type="button" onClick={() => close(true)}>
                {options.confirmLabel ?? "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </ConfirmContext.Provider>
  );
}

function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const notify = useCallback<Notify>((message, tone = "success") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, tone, message }].slice(-3));
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 4200);
  }, []);

  return (
    <NotificationContext.Provider value={notify}>
      {children}
      <ToastStack toasts={toasts} dismiss={(id) => setToasts((current) => current.filter((toast) => toast.id !== id))} />
    </NotificationContext.Provider>
  );
}

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

const lpFeatures = [
  {
    icon: MonitorCheck,
    title: "Uptime & API checks",
    text: "HTTP checks with expected status codes, keyword and nested-JSON assertions, response headers, and per-monitor latency budgets.",
  },
  {
    icon: ShieldCheck,
    title: "SSL, DNS & TCP monitoring",
    text: "Certificate expiry warnings before they burn you, DNS record checks with expected values, and port connectivity probes.",
  },
  {
    icon: RadioTower,
    title: "Heartbeats for cron jobs",
    text: "Get a unique URL, ping it from your scheduled jobs, and we raise the alarm when a backup or worker silently never runs.",
  },
  {
    icon: AlertTriangle,
    title: "Incidents with receipts",
    text: "Failures above threshold open incidents with the reason, duration, and an acknowledge/resolve trail — so post-mortems write themselves.",
  },
  {
    icon: ScrollText,
    title: "Centralized logs",
    text: "Ship structured logs from any app; secrets are redacted on ingest, everything is searchable, and error-frequency charts come free.",
  },
  {
    icon: Server,
    title: "Infrastructure & traces",
    text: "A lightweight agent reports CPU, memory, disk, and services with alert thresholds — plus OpenTelemetry traces, service maps, and SLOs.",
  },
];

const lpSteps = [
  {
    num: "01",
    title: "Point WATCHDOG at your stack",
    text: "Websites, APIs, SSL certificates, DNS records, TCP ports, cron heartbeats — organized with environments and tags per client.",
  },
  {
    num: "02",
    title: "We keep watch",
    text: "Checks run on schedule with retries and rate limits. Incidents open automatically, your apps ship us logs, and hosts report metrics.",
  },
  {
    num: "03",
    title: "You hear it first",
    text: "Email and Telegram alerts fan out with the reason attached — plus SLO budgets, anomaly alerts, and client-ready status pages.",
  },
];

function LandingPage() {
  return (
    <div className="landing-page">
      <div className="landing">
        <nav className="topbar">
          <Link className="brand" to="/">
            <LogoMark size={26} mono />
            WATCHDOG
          </Link>
          <div className="nav-actions">
            <Link to="/login">Log in</Link>
            <Link className="button inverse" to="/register">
              Create account
            </Link>
          </div>
        </nav>
        <section className="hero">
          <div className="hero-copy">
            <span className="eyebrow">Monitoring &amp; observability for agencies</span>
            <h1>Know it&apos;s down before your clients do.</h1>
            <p>
              WATCHDOG watches your websites, APIs, certificates, cron jobs, servers, and
              application logs — and alerts you the moment anything breaks. Full-stack
              observability, built for agencies that run the internet for other people.
            </p>
            <div className="hero-actions">
              <Link className="button primary lg" to="/register">
                Start monitoring free
              </Link>
              <a className="button inverse lg" href="#features">
                See how it works
              </a>
            </div>
            <ul className="hero-points">
              <li>
                <CheckCircle2 size={15} /> SSL, DNS &amp; TCP checks
              </li>
              <li>
                <CheckCircle2 size={15} /> Logs, metrics &amp; traces
              </li>
              <li>
                <CheckCircle2 size={15} /> Status pages &amp; client reports
              </li>
            </ul>
          </div>
          <div className="hero-shot">
            <div className="browser-frame">
              <div className="browser-bar">
                <span className="dot red" />
                <span className="dot amber" />
                <span className="dot green" />
                <span className="url-pill">watchdog.clevermike.studio/app</span>
              </div>
              <img
                src="/screenshots/dashboard-overview.png"
                alt="WATCHDOG dashboard showing monitor stats, activity, and an open incident"
              />
            </div>
          </div>
        </section>
      </div>

      <section className="lp-features" id="features">
        <span className="eyebrow">Everything in one place</span>
        <h2>Built for the way agencies run the internet</h2>
        <div className="lp-grid">
          {lpFeatures.map((feature) => (
            <article className="lp-card" key={feature.title}>
              <feature.icon size={22} />
              <h3>{feature.title}</h3>
              <p>{feature.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-showcase">
        <div className="lp-showcase-copy">
          <span className="eyebrow">Incidents &amp; alerting</span>
          <h2>Downtime becomes a quick fix, not a Monday surprise</h2>
          <p>
            Monitors are grouped by client, checked on schedule, and every failure is tracked
            to resolution. Your team sees the same truth your status page shows.
          </p>
          <ul>
            <li>
              <CheckCircle2 size={16} /> Failures open incidents automatically
            </li>
            <li>
              <CheckCircle2 size={16} /> Alert channels fan out to email and Telegram
            </li>
            <li>
              <CheckCircle2 size={16} /> Acknowledge and resolve with one click
            </li>
          </ul>
        </div>
        <div className="lp-showcase-shot">
          <div className="browser-frame">
            <div className="browser-bar">
              <span className="dot red" />
              <span className="dot amber" />
              <span className="dot green" />
              <span className="url-pill">watchdog.clevermike.studio/app/monitors</span>
            </div>
            <img
              src="/screenshots/dashboard-monitors.png"
              alt="WATCHDOG monitor list showing UP and DOWN statuses per client site"
              loading="lazy"
            />
          </div>
        </div>
      </section>

      <section className="lp-steps">
        <span className="eyebrow">How it works</span>
        <h2>Live in three minutes</h2>
        <ol className="lp-steps-grid">
          {lpSteps.map((step) => (
            <li className="lp-step" key={step.num}>
              <span className="num">{step.num}</span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="lp-cta">
        <div className="lp-cta-panel">
          <h2>Your clients are sleeping. Their sites shouldn&apos;t be.</h2>
          <p>Set up your first monitor before your coffee cools.</p>
          <Link className="button inverse lg" to="/register">
            Create your account
          </Link>
        </div>
      </section>

      <footer className="lp-footer">
        <Link className="brand" to="/">
          <LogoMark size={20} />
          WATCHDOG
        </Link>
        <nav>
          <Link to="/login">Log in</Link>
          <Link to="/register">Create account</Link>
          <a href="https://watchdog.clevermike.studio/">watchdog.clevermike.studio</a>
        </nav>
        <small>© {new Date().getFullYear()} WATCHDOG. All rights reserved.</small>
      </footer>
    </div>
  );
}

function AuthPage({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const notify = useNotify();
  const routeNotice =
    typeof (location.state as { notice?: unknown } | null)?.notice === "string"
      ? String((location.state as { notice: string }).notice)
      : "";
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verificationEmail, setVerificationEmail] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [notice, setNotice] = useState(routeNotice);
  const queryClient = useQueryClient();
  useEffect(() => {
    setNotice(routeNotice);
  }, [routeNotice]);
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
        notify(`Welcome back, ${data.user.full_name}.`);
        navigate("/app");
        return;
      }
      setVerificationEmail(data.user.email);
      setNotice(data.message);
      notify(data.message, "info");
    },
  });
  const verifyMutation = useMutation({
    mutationFn: () => authService.verifyEmail({ email: verificationEmail, code: verificationCode }),
    onSuccess: () => {
      notify("Email verified. You can log in now.");
      navigate("/login", { state: { notice: "Email verified. You can log in now." } });
    },
  });
  const resendMutation = useMutation({
    mutationFn: () => authService.resendVerification({ email: verificationEmail || email }),
    onSuccess: (data) => {
      setVerificationEmail(data.user.email);
      setNotice(data.message);
      notify(data.message, "info");
    },
  });

  if (mode === "register" && verificationEmail) {
    return (
      <main className="auth-shell">
        <Link className="brand" to="/">
          <LogoMark size={26} />
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
          {notice ? <p className="notice-text">{notice}</p> : null}
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
        <LogoMark size={26} />
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
        {notice ? <p className="notice-text">{notice}</p> : null}
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
        {mode === "register" ? <p className="field-hint">Use at least 8 characters.</p> : null}
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
  const notify = useNotify();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [notice, setNotice] = useState("");
  const requestMutation = useMutation({
    mutationFn: () => authService.forgotPassword({ email }),
    onSuccess: (data) => {
      setCodeSent(true);
      setNotice(data.message);
      notify(data.message, "info");
    },
  });
  const resetMutation = useMutation({
    mutationFn: () => authService.resetPassword({ email, code, new_password: newPassword }),
    onSuccess: () => {
      notify("Password reset. Log in with your new password.");
      navigate("/login", { state: { notice: "Password reset. Log in with your new password." } });
    },
  });

  return (
    <main className="auth-shell">
      <Link className="brand" to="/">
        <LogoMark size={26} />
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
        {notice ? <p className="notice-text">{notice}</p> : null}
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
  const notify = useNotify();
  const navItems = [
    { to: "/app", label: "Overview", icon: Home },
    { to: "/app/monitors", label: "Monitors", icon: MonitorCheck },
    { to: "/app/health", label: "Service Health", icon: Activity },
    { to: "/app/alerts", label: "Alerts", icon: Bell },
    { to: "/app/incidents", label: "Incidents", icon: AlertTriangle },
    { to: "/app/clients", label: "Clients", icon: Users },
    { to: "/app/maintenance", label: "Maintenance", icon: Wrench },
    { to: "/app/logs", label: "Logs", icon: ScrollText },
    { to: "/app/infrastructure", label: "Infrastructure", icon: Server },
    { to: "/app/traces", label: "Traces", icon: Network },
    { to: "/app/slos", label: "SLOs", icon: Target },
    { to: "/app/dashboards", label: "Dashboards", icon: LayoutDashboard },
    { to: "/app/alert-channels", label: "Alert Channels", icon: Bell },
    { to: "/app/api-keys", label: "API Keys", icon: KeyRound },
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
    notify("Logged out.");
    navigate("/login", { state: { notice: "Logged out." } });
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
              <LogoMark size={26} />
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
              {organizations.length ? (
                <select
                  value={selected?.public_id ?? ""}
                  onChange={(event) => {
                    localStorage.setItem("watchdog_organization_public_id", event.target.value);
                    queryClient.invalidateQueries();
                    notify("Workspace switched.", "info");
                  }}
                >
                  {organizations.map((organization) => (
                    <option key={organization.public_id} value={organization.public_id}>
                      {organization.name}
                    </option>
                  ))}
                </select>
              ) : (
                <select disabled aria-label="No workspace yet">
                  <option>No organization yet</option>
                </select>
              )}
            </div>
            <div className="header-actions">
              {organizations.length ? (
                <Link className="button secondary" to="/app/organizations/new">
                  <Building2 size={16} />
                  Organization
                </Link>
              ) : null}
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
              <Route path="/maintenance" element={<MaintenancePage organization={selected} />} />
              <Route path="/logs" element={<LogsPage organization={selected} />} />
              <Route path="/infrastructure" element={<InfrastructurePage organization={selected} />} />
              <Route path="/traces" element={<TracesPage organization={selected} />} />
              <Route path="/slos" element={<SlosPage organization={selected} />} />
              <Route path="/dashboards" element={<DashboardsPage organization={selected} />} />
              <Route path="/health" element={<HealthPage organization={selected} />} />
              <Route path="/api-keys" element={<ApiKeysPage organization={selected} />} />
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
  const notify = useNotify();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const mutation = useMutation({
    mutationFn: () => organizationService.create({ name, slug: slug || slugify(name) }),
    onSuccess: (organization) => {
      localStorage.setItem("watchdog_organization_public_id", organization.public_id);
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      notify(`${organization.name} created.`);
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
  const recentChecks = useQuery({
    queryKey: ["recent-checks", organization.public_id],
    queryFn: () => checkService.recent(organization.public_id, 300),
  });
  const data = stats.data;
  const failedRate = data?.total_checks ? Math.round((data.failed_checks / data.total_checks) * 100) : 0;
  const chartData = useMemo(() => {
    const nameById = new Map<number, string>();
    for (const monitor of monitors.data?.monitors ?? []) {
      nameById.set(monitor.id, monitor.name);
    }
    const counts = new Map<number, { checks: number; failures: number }>();
    for (const check of recentChecks.data?.results ?? []) {
      const entry = counts.get(check.monitor_id) ?? { checks: 0, failures: 0 };
      entry.checks += 1;
      if (!check.success) entry.failures += 1;
      counts.set(check.monitor_id, entry);
    }
    return [...counts.entries()]
      .map(([monitorId, value]) => ({
        name: nameById.get(monitorId) ?? `Monitor #${monitorId}`,
        checks: value.checks,
        failures: value.failures,
      }))
      .sort((a, b) => b.checks - a.checks)
      .slice(0, 8);
  }, [recentChecks.data, monitors.data]);
  const maxChecks = Math.max(1, ...chartData.map((item) => item.checks));

  return (
    <section>
      <PageHeader title="Overview" description="Current health across monitors, incidents, and alerts." />
      {stats.isLoading ? <SkeletonGrid /> : null}
      {stats.isError ? <ErrorBox message={unwrapError(stats.error)} /> : null}
      {data ? (
        <>
          {monitors.data && !monitors.data.monitors.length ? (
            <div className="cta-panel">
              <div>
                <h2>Create your first monitor</h2>
                <p>Add a website, API, or heartbeat job to start tracking uptime.</p>
              </div>
              <Link className="button primary" to="/app/monitors/new">
                <Plus size={16} />
                New monitor
              </Link>
            </div>
          ) : null}
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
                      <span>
                        {item.name}
                        {item.failures ? ` · ${item.failures} failed` : ""}
                      </span>
                      <div>
                        <i style={{ width: `${(item.checks / maxChecks) * 100}%` }} />
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
  const notify = useNotify();
  const confirmAction = useConfirm();
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [environmentFilter, setEnvironmentFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  // Hooks must run unconditionally: the query stays registered even when no
  // organization is selected yet, otherwise React throws "rendered more hooks".
  const query = useQuery({
    queryKey: ["monitors", organization?.public_id, typeFilter, statusFilter, environmentFilter, tagFilter],
    queryFn: () =>
      monitorService.list(organization!.public_id, {
        monitor_type: typeFilter || undefined,
        status: statusFilter || undefined,
        environment: environmentFilter || undefined,
        tag: tagFilter || undefined,
      }),
    enabled: Boolean(organization),
  });
  const remove = useMutation({
    mutationFn: (id: string) => monitorService.remove(id),
    onSuccess: (_data, id) => {
      const monitor = (query.data?.monitors ?? []).find((item) => item.public_id === id);
      queryClient.invalidateQueries({ queryKey: ["monitors"] });
      notify(`${monitor?.name ?? "Monitor"} deleted.`);
    },
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const monitors = query.data?.monitors ?? [];

  return (
    <section>
      <PageHeader title="Monitors" description="Websites, APIs, SSL certificates, DNS records, TCP ports, and heartbeat jobs in this workspace.">
        <Link className="button primary" to="/app/monitors/new">
          <Plus size={16} />
          New monitor
        </Link>
      </PageHeader>
      <form
        className="filter-row"
        onSubmit={(event) => {
          event.preventDefault();
          query.refetch();
        }}
      >
        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
          <option value="">All types</option>
          {["WEBSITE", "API", "HEARTBEAT", "SSL", "DNS", "TCP"].map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="">All statuses</option>
          {["UP", "DOWN", "DEGRADED", "PAUSED", "MAINTENANCE", "UNKNOWN"].map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
        <input
          placeholder="Environment"
          value={environmentFilter}
          onChange={(event) => setEnvironmentFilter(event.target.value)}
        />
        <input placeholder="Tag" value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} />
        <button className="button secondary compact" type="submit">
          Filter
        </button>
      </form>
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
                aria-label={`Delete monitor ${monitor.name}`}
                disabled={remove.isPending}
                onClick={() => {
                  confirmAction({
                    title: `Delete monitor "${monitor.name}"?`,
                    message: "Its check history and incidents will remain in reports.",
                  }).then((confirmed) => {
                    if (confirmed) {
                      remove.mutate(monitor.public_id);
                    }
                  });
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
  const notify = useNotify();
  const [type, setType] = useState<MonitorType>("WEBSITE");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("GET");
  const [interval, setIntervalValue] = useState(300);
  const [expectedStatus, setExpectedStatus] = useState(200);
  const [expectedText, setExpectedText] = useState("");
  const [requestBody, setRequestBody] = useState("");
  const [clientId, setClientId] = useState("");
  const [environment, setEnvironment] = useState("");
  const [tags, setTags] = useState("");
  const [sslThresholdDays, setSslThresholdDays] = useState(14);
  const [port, setPort] = useState("");
  const [recordType, setRecordType] = useState<DnsRecordType>("A");
  const [expectedValues, setExpectedValues] = useState("");
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
        environment: environment || null,
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
        ...(type === "SSL" ? { ssl_expiry_threshold_days: sslThresholdDays } : {}),
        ...(type === "TCP" ? { port: port ? Number(port) : null } : {}),
        ...(type === "DNS"
          ? { record_type: recordType, expected_values: expectedValues.split("\n").map((line) => line.trim()).filter(Boolean) }
          : {}),
      })
      );
    },
    onSuccess: (monitor) => {
      setCreated(monitor);
      queryClient.invalidateQueries({ queryKey: ["monitors", organization?.public_id] });
      if (monitor.monitor_type !== "HEARTBEAT") {
        notify(`${monitor.name} created.`);
        navigate("/app/monitors");
      } else {
        notify(`${monitor.name} created. Copy the heartbeat URL to start reporting.`);
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
        description={`Create a website, API, SSL, DNS, TCP, or heartbeat monitor in ${organization.name}.`}
      />
      <form
        className="form-panel wide"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <div className="segmented">
          {(["WEBSITE", "API", "HEARTBEAT", "SSL", "DNS", "TCP"] as MonitorType[]).map((option) => (
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
            {type === "TCP" ? "Target host (e.g. tcp://db.example.com)" : type === "DNS" ? "Domain (e.g. example.com)" : "Target URL"}
            <input
              type={type === "WEBSITE" || type === "API" ? "url" : "text"}
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              required
            />
          </label>
        ) : null}
        {type !== "HEARTBEAT" ? (
          <p className="field-hint">
            Public targets only — localhost and private network addresses are blocked.
          </p>
        ) : null}
        <div className="form-grid">
          {type === "WEBSITE" || type === "API" ? (
            <label>
              Method
              <select value={method} onChange={(event) => setMethod(event.target.value)}>
                {["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"].map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            </label>
          ) : null}
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
          {type === "WEBSITE" || type === "API" ? (
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
          {type === "SSL" ? (
            <label>
              Warn when expiring within (days)
              <input
                type="number"
                min={1}
                max={365}
                value={sslThresholdDays}
                onChange={(event) => setSslThresholdDays(Number(event.target.value))}
              />
            </label>
          ) : null}
          {type === "TCP" ? (
            <label>
              Port
              <input
                type="number"
                min={1}
                max={65535}
                value={port}
                onChange={(event) => setPort(event.target.value)}
                required
              />
            </label>
          ) : null}
          {type === "DNS" ? (
            <label>
              Record type
              <select value={recordType} onChange={(event) => setRecordType(event.target.value as DnsRecordType)}>
                {DNS_RECORD_TYPES.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
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
        {type === "DNS" ? (
          <label>
            Expected values (one per line, optional)
            <textarea
              value={expectedValues}
              onChange={(event) => setExpectedValues(event.target.value)}
              placeholder={"93.184.216.34"}
            />
          </label>
        ) : null}
        <div className="form-grid">
          <label>
            Environment (optional)
            <input
              value={environment}
              onChange={(event) => setEnvironment(event.target.value)}
              placeholder="production"
            />
          </label>
          <label>
            Tags (comma-separated, optional)
            <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="critical, payments" />
          </label>
        </div>
        {mutation.isError ? <p className="error-text">{unwrapError(mutation.error)}</p> : null}
        <button className="button primary">Create monitor</button>
      </form>
      {created?.heartbeat_url ? (
        <section className="panel success-panel">
          <h2>Heartbeat URL</h2>
          <code>{`${location.origin.replace("5173", "8000")}${created.heartbeat_url}`}</code>
          <button
            className="button secondary"
            onClick={() => {
              navigator.clipboard.writeText(`${location.origin.replace("5173", "8000")}${created.heartbeat_url}`);
              notify("Heartbeat URL copied.");
            }}
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
  const notify = useNotify();
  const confirmAction = useConfirm();
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
    onSuccess: (updated) => {
      refreshMonitor();
      notify(`${updated.name} paused.`);
    },
  });
  const resume = useMutation({
    mutationFn: () => monitorService.resume(monitorId),
    onSuccess: (updated) => {
      refreshMonitor();
      notify(`${updated.name} resumed.`);
    },
  });
  const runCheck = useMutation({
    mutationFn: () => monitorService.runCheck(monitorId),
    onSuccess: (result) => {
      refreshMonitor();
      notify(result.success ? "Check completed successfully." : "Check completed with a failure.", result.success ? "success" : "info");
    },
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
    onSuccess: (updated) => {
      refreshMonitor();
      notify(`${updated.name} updated.`);
    },
  });
  const remove = useMutation({
    mutationFn: () => monitorService.remove(monitorId),
    onSuccess: () => {
      notify(`${monitor?.name ?? "Monitor"} deleted.`);
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
              className="button danger"
              disabled={remove.isPending}
              onClick={() => {
                confirmAction({
                  title: `Delete monitor "${monitor.name}"?`,
                  message: "Its check history and incidents will remain in reports.",
                }).then((confirmed) => {
                  if (confirmed) {
                    remove.mutate();
                  }
                });
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
                {monitor.environment ? (
                  <>
                    <dt>Environment</dt>
                    <dd>{monitor.environment}</dd>
                  </>
                ) : null}
                {monitor.tags?.length ? (
                  <>
                    <dt>Tags</dt>
                    <dd>{monitor.tags.join(", ")}</dd>
                  </>
                ) : null}
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
            {monitor.ssl_expires_at ? (
              <section className="panel">
                <h2>SSL certificate</h2>
                <div className="metric-grid auto-fit">
                  <Metric
                    label="Expires"
                    value={formatDate(monitor.ssl_expires_at)}
                    icon={Clock}
                    tone={new Date(monitor.ssl_expires_at).getTime() < Date.now() ? "bad" : "ok"}
                  />
                  <Metric
                    label="Days remaining"
                    value={Math.round((new Date(monitor.ssl_expires_at).getTime() - Date.now()) / 86400000)}
                    icon={Gauge}
                  />
                  <Metric label="Issuer" value={monitor.ssl_issuer ?? "—"} icon={CheckCircle2} />
                </div>
              </section>
            ) : null}
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
  const notify = useNotify();
  const query = useQuery({
    queryKey: ["alerts", organization?.public_id],
    queryFn: () => alertService.list(organization?.public_id),
    enabled: Boolean(organization),
  });
  const acknowledge = useMutation({
    mutationFn: (id: number) => alertService.acknowledge(id),
    onSuccess: (alert) => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      notify(`${alert.title} acknowledged.`);
    },
  });
  const resolve = useMutation({
    mutationFn: (id: number) => alertService.resolve(id),
    onSuccess: (alert) => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      notify(`${alert.title} resolved.`);
    },
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
  const notify = useNotify();
  const query = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => incidentService.get(incidentId),
  });
  const acknowledge = useMutation({
    mutationFn: () => incidentService.acknowledge(incidentId, "Acknowledged from dashboard"),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      notify(`${incident.title} acknowledged.`);
    },
  });
  const resolve = useMutation({
    mutationFn: () => incidentService.resolve(incidentId, "Resolved from dashboard"),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      notify(`${incident.title} resolved.`);
    },
  });
  const incident = query.data;
  const timeline = useQuery({
    queryKey: ["incident-timeline", incidentId],
    queryFn: () => analyticsService.incidentTimeline(incidentId),
  });

  return (
    <section>
      {query.isLoading ? <SkeletonGrid /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {incident ? (
        <>
          <PageHeader title={incident.title} description={incident.reason}>
            <button className="button secondary" disabled={acknowledge.isPending} onClick={() => acknowledge.mutate()}>
              Acknowledge
            </button>
            <button className="button primary" disabled={resolve.isPending} onClick={() => resolve.mutate()}>
              Resolve
            </button>
          </PageHeader>
          {acknowledge.isError ? <ErrorBox message={unwrapError(acknowledge.error)} /> : null}
          {resolve.isError ? <ErrorBox message={unwrapError(resolve.error)} /> : null}
          <div className="metric-grid">
            <Metric label="Status" value={incident.status} icon={AlertTriangle} />
            <Metric label="Severity" value={incident.severity} icon={Gauge} />
            <Metric label="Started" value={formatDate(incident.started_at)} icon={Clock} />
            <Metric label="Resolved" value={formatDate(incident.resolved_at)} icon={CheckCircle2} tone="ok" />
          </div>
          <section className="panel">
            <h2>Correlated timeline</h2>
            <p className="field-hint">
              Updates, alerts, failed checks, and related application log errors in one chronological view.
            </p>
            {timeline.isLoading ? <TableSkeleton /> : null}
            {timeline.isError ? <ErrorBox message={unwrapError(timeline.error)} /> : null}
            {timeline.data?.events.length ? (
              <div className="list-stack">
                {timeline.data.events.map((event, index) => (
                  <div key={index} className="list-row">
                    <strong>{formatDate(event.timestamp)}</strong>
                    <span className={event.kind === "alert" ? "status warn" : event.kind === "check" ? "status bad" : "status"}>
                      {event.kind.toUpperCase()}
                    </span>
                    <span>{event.message}</span>
                  </div>
                ))}
              </div>
            ) : null}
            {!timeline.isLoading && !(timeline.data?.events.length ?? 0) ? (
              <EmptyInline text="No timeline events yet." />
            ) : null}
          </section>
        </>
      ) : null}
    </section>
  );
}

function AlertChannels({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
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
      notify("Alert channel created.");
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
      notify("Alert channel updated.");
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
        <input placeholder="Channel name" aria-label="Channel name" value={name} onChange={(event) => setName(event.target.value)} required />
        <select aria-label="Channel type" value={type} onChange={(event) => setType(event.target.value as NotificationChannel["channel_type"])}>
          <option>EMAIL</option>
          <option>TELEGRAM</option>
        </select>
        <input
          placeholder={type === "EMAIL" ? "alerts@example.com" : "Telegram chat ID"}
          aria-label={type === "EMAIL" ? "Alert email address" : "Telegram chat ID"}
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
          <input aria-label="Channel name" value={editName} onChange={(event) => setEditName(event.target.value)} required />
          <input
            aria-label={editing.channel_type === "EMAIL" ? "Alert email address" : "Telegram chat ID"}
            value={editTarget}
            onChange={(event) => setEditTarget(event.target.value)}
            required
          />
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
  const notify = useNotify();
  const confirmAction = useConfirm();
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
      notify("Client created.");
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
      notify("Client updated.");
    },
  });
  const remove = useMutation({
    mutationFn: (clientId: string) => clientService.remove(organization!.public_id, clientId),
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      notify("Client deleted.");
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
        <input placeholder="Client name" aria-label="Client name" value={name} onChange={(event) => setName(event.target.value)} required />
        <input type="email" placeholder="Contact email" aria-label="Contact email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <input placeholder="Notes" aria-label="Notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
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
          <input aria-label="Client name" value={editName} onChange={(event) => setEditName(event.target.value)} required />
          <input type="email" aria-label="Contact email" value={editEmail} onChange={(event) => setEditEmail(event.target.value)} />
          <input aria-label="Notes" value={editNotes} onChange={(event) => setEditNotes(event.target.value)} />
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
                aria-label={`Edit client ${client.name}`}
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
                aria-label={`Delete client ${client.name}`}
                disabled={remove.isPending}
                onClick={() => {
                  confirmAction({
                    title: `Delete client "${client.name}"?`,
                  }).then((confirmed) => {
                    if (confirmed) {
                      remove.mutate(client.public_id);
                    }
                  });
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
  const notify = useNotify();
  const confirmAction = useConfirm();
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
      notify("Status page created.");
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
      notify("Status page updated.");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => statusPageService.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["status-pages"] });
      notify("Status page deleted.");
    },
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
          aria-label="Page name"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setSlug(slugify(event.target.value));
          }}
          required
        />
        <input placeholder="slug" aria-label="Slug" value={slug} onChange={(event) => setSlug(slugify(event.target.value))} required />
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
          <input aria-label="Page name" value={editName} onChange={(event) => setEditName(event.target.value)} required />
          <input aria-label="Slug" value={editSlug} onChange={(event) => setEditSlug(slugify(event.target.value))} required />
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
                    aria-label={`Copy public link for ${page.name}`}
                    onClick={() => {
                      navigator.clipboard.writeText(publicUrl);
                      notify("Public status link copied.");
                    }}
                  >
                    <Copy size={16} />
                  </button>
                  <Link
                    className="icon-button"
                    title="Open public page"
                    aria-label={`Open public page for ${page.name}`}
                    to={publicPath}
                    target="_blank"
                  >
                    <ExternalLink size={16} />
                  </Link>
                  <button
                    className="icon-button"
                    title="Edit status page"
                    aria-label={`Edit status page ${page.name}`}
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
                    aria-label={`Delete status page ${page.name}`}
                    disabled={remove.isPending}
                    onClick={() => {
                      confirmAction({
                        title: `Delete status page "${page.name}"?`,
                      }).then((confirmed) => {
                        if (confirmed) {
                          remove.mutate(page.public_id);
                        }
                      });
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
  const notify = useNotify();
  const confirmAction = useConfirm();
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
      notify(`Service added to ${page.name}.`);
    },
  });
  const removeService = useMutation({
    mutationFn: (serviceId: string) => statusPageService.removeService(page.public_id, serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["status-page-services", page.public_id] });
      queryClient.invalidateQueries({ queryKey: ["public-status-page", page.slug] });
      notify(`Service removed from ${page.name}.`);
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
                aria-label={`Remove ${service.display_name} from ${page.name}`}
                disabled={removeService.isPending}
                onClick={() => {
                  confirmAction({
                    title: `Remove "${service.display_name}" from ${page.name}?`,
                  }).then((confirmed) => {
                    if (confirmed) {
                      removeService.mutate(service.public_id);
                    }
                  });
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
          <footer className="public-footer">
            <LogoMark size={15} />
            <span>
              Powered by <Link to="/">WATCHDOG</Link>
            </span>
          </footer>
        </section>
      ) : null}
    </main>
  );
}

function ChannelActions({ channel, onEdit }: { channel: NotificationChannel; onEdit: () => void }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const confirmAction = useConfirm();
  const test = useMutation({
    mutationFn: () => alertChannelService.test(channel.id),
    onSuccess: () => notify(`Test alert queued for ${channel.name}.`),
  });
  const remove = useMutation({
    mutationFn: () => alertChannelService.remove(channel.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-channels"] });
      notify(`${channel.name} deleted.`);
    },
  });
  return (
    <div className="row-actions">
      <button
        className="icon-button"
        title="Send test alert"
        aria-label={`Send test alert to ${channel.name}`}
        disabled={test.isPending}
        onClick={() => test.mutate()}
      >
        <Bell size={16} />
      </button>
      <button className="icon-button" title="Edit channel" aria-label={`Edit channel ${channel.name}`} onClick={onEdit}>
        <Pencil size={16} />
      </button>
      <button
        className="icon-button"
        title="Delete channel"
        aria-label={`Delete channel ${channel.name}`}
        disabled={remove.isPending}
        onClick={() => {
          confirmAction({
            title: `Delete alert channel "${channel.name}"?`,
          }).then((confirmed) => {
            if (confirmed) {
              remove.mutate();
            }
          });
        }}
      >
        <Trash2 size={16} />
      </button>
    </div>
  );
}

const DNS_RECORD_TYPES: DnsRecordType[] = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "SRV", "PTR"];

function levelClass(level: string) {
  const normalized = level.toUpperCase();
  if (normalized === "ERROR" || normalized === "CRITICAL") return "status bad";
  if (normalized === "WARNING") return "status warn";
  if (normalized === "INFO") return "status ok";
  return "status";
}

function healthClass(health: string) {
  if (health === "OK") return "status ok";
  if (health === "WARNING") return "status warn";
  if (health === "CRITICAL") return "status bad";
  return "status";
}

function toIso(value: string) {
  return value ? new Date(value).toISOString() : null;
}

function MaintenancePage({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const confirmAction = useConfirm();
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [monitorIds, setMonitorIds] = useState<string[]>([]);
  const monitors = useQuery({
    queryKey: ["monitors", organization?.public_id],
    queryFn: () => monitorService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const query = useQuery({
    queryKey: ["maintenance-windows", organization?.public_id],
    queryFn: () => maintenanceWindowService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const create = useMutation({
    mutationFn: () =>
      maintenanceWindowService.create({
        organization_id: organization!.public_id,
        title,
        description: description || null,
        starts_at: toIso(startsAt),
        ends_at: toIso(endsAt),
        notify_subscribers: false,
        monitor_ids: monitorIds,
      }),
    onSuccess: (window) => {
      queryClient.invalidateQueries({ queryKey: ["maintenance-windows"] });
      notify(`Maintenance window "${window.title}" created.`);
      setShowForm(false);
      setTitle("");
      setDescription("");
      setStartsAt("");
      setEndsAt("");
      setMonitorIds([]);
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => maintenanceWindowService.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["maintenance-windows"] });
      notify("Maintenance window deleted.");
    },
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const windows = query.data?.windows ?? [];
  const now = Date.now();
  const windowState = (window: MaintenanceWindow) =>
    new Date(window.ends_at).getTime() <= now
      ? "COMPLETED"
      : new Date(window.starts_at).getTime() <= now
        ? "IN_PROGRESS"
        : "SCHEDULED";

  return (
    <section>
      <PageHeader
        title="Maintenance windows"
        description="Scheduled windows pause checks, incidents, and missed-heartbeat alerts for covered monitors."
      >
        <button className="button primary" onClick={() => setShowForm((open) => !open)}>
          <Plus size={16} />
          New window
        </button>
      </PageHeader>
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {create.isError ? <ErrorBox message={unwrapError(create.error)} /> : null}
      {remove.isError ? <ErrorBox message={unwrapError(remove.error)} /> : null}
      {showForm ? (
        <form
          className="form-panel wide"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} required />
          </label>
          <label>
            Description
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <div className="form-grid">
            <label>
              Starts at
              <input
                type="datetime-local"
                value={startsAt}
                onChange={(event) => setStartsAt(event.target.value)}
                required
              />
            </label>
            <label>
              Ends at
              <input
                type="datetime-local"
                value={endsAt}
                onChange={(event) => setEndsAt(event.target.value)}
                required
              />
            </label>
          </div>
          <fieldset className="field-group">
            <legend>Covered monitors (none selected = whole workspace)</legend>
            <div className="checkbox-grid">
              {(monitors.data?.monitors ?? []).map((monitor) => (
                <label key={monitor.public_id} className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={monitorIds.includes(monitor.public_id)}
                    onChange={(event) => {
                      setMonitorIds((current) =>
                        event.target.checked
                          ? [...current, monitor.public_id]
                          : current.filter((id) => id !== monitor.public_id),
                      );
                    }}
                  />
                  {monitor.name}
                </label>
              ))}
            </div>
          </fieldset>
          {create.isPending ? <p className="field-hint">Creating…</p> : null}
          <button className="button primary" disabled={create.isPending}>
            Create window
          </button>
        </form>
      ) : null}
      {!query.isLoading && !windows.length ? (
        <EmptyInline text="No maintenance windows scheduled." />
      ) : null}
      {windows.length ? (
        <DataTable
          headers={["Title", "State", "Starts", "Ends", "Monitors", ""]}
          rows={windows.map((window) => [
            window.title,
            <span
              className={
                windowState(window) === "IN_PROGRESS"
                  ? "status warn"
                  : windowState(window) === "SCHEDULED"
                    ? "status info"
                    : "status"
              }
            >
              {windowState(window)}
            </span>,
            formatDate(window.starts_at),
            formatDate(window.ends_at),
            window.monitor_ids.length
              ? `${window.monitor_ids.length} monitor${window.monitor_ids.length === 1 ? "" : "s"}`
              : "Whole workspace",
            <div className="row-actions">
              <button
                className="icon-button"
                title="Delete window"
                aria-label={`Delete maintenance window ${window.title}`}
                disabled={remove.isPending}
                onClick={() => {
                  confirmAction({
                    title: `Delete maintenance window "${window.title}"?`,
                    message: "Covered monitors will resume normal checking.",
                  }).then((confirmed) => {
                    if (confirmed) {
                      remove.mutate(window.id);
                    }
                  });
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

function LogsPage({ organization }: { organization?: Organization }) {
  const [application, setApplication] = useState("");
  const [level, setLevel] = useState("");
  const [search, setSearch] = useState("");
  const stats = useQuery({
    queryKey: ["log-stats", organization?.public_id],
    queryFn: () => logService.stats(organization!.public_id),
    enabled: Boolean(organization),
  });
  const query = useQuery({
    queryKey: ["logs", organization?.public_id, application, level, search],
    queryFn: () =>
      logService.list({
        organizationId: organization!.public_id,
        application: application || undefined,
        level: level || undefined,
        search: search || undefined,
        limit: 200,
      }),
    enabled: Boolean(organization),
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const logs = query.data?.logs ?? [];
  const statsData = stats.data;
  const maxVolume = Math.max(1, ...(statsData?.volume ?? []).map((point) => point.total));
  const totalLogs = statsData?.total ?? 0;

  return (
    <section>
      <PageHeader
        title="Logs"
        description="Application logs ingested through the log API — searchable, filtered, and redacted."
      />
      {stats.isLoading ? <SkeletonGrid /> : null}
      {stats.isError ? <ErrorBox message={unwrapError(stats.error)} /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {statsData ? (
        <div className="metric-grid">
          <Metric label="Log lines (24h)" value={statsData.total} icon={ScrollText} />
          <Metric label="Errors" value={statsData.error_count} icon={AlertTriangle} tone={statsData.error_count ? "bad" : "ok"} />
          <Metric label="Applications" value={statsData.applications || "—"} icon={Server} />
          <Metric label="Debug/Info" value={(statsData.by_level.INFO ?? 0) + (statsData.by_level.DEBUG ?? 0)} icon={CheckCircle2} tone="ok" />
        </div>
      ) : null}
      {statsData && statsData.volume.length ? (
        <div className="panel">
          <h3>Volume (24h, buckets of time)</h3>
          <div className="volume-chart" role="img" aria-label="Log volume over time">
            {statsData.volume.map((point) => (
              <div
                key={point.bucket}
                className="volume-col"
                title={`${point.total} lines, ${point.error} errors`}
              >
                <div className="volume-err" style={{ height: `${(point.error / maxVolume) * 100}%` }} />
                <div className="volume-total" style={{ height: `${(point.total / maxVolume) * 100}%` }} />
              </div>
            ))}
          </div>
          <p className="field-hint">Red segments are errors; grey segments are total volume.</p>
        </div>
      ) : null}
      <form
        className="filter-row"
        onSubmit={(event) => {
          event.preventDefault();
          query.refetch();
        }}
      >
        <input
          placeholder="Application"
          value={application}
          onChange={(event) => setApplication(event.target.value)}
        />
        <select value={level} onChange={(event) => setLevel(event.target.value)}>
          <option value="">All levels</option>
          {["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
        <input
          placeholder="Search messages…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <button className="button secondary compact" type="submit">
          Apply
        </button>
      </form>
      {totalLogs > 0 && !logs.length ? <EmptyInline text="No logs match these filters." /> : null}
      {!query.isLoading && !totalLogs ? <EmptyInline text="No logs ingested yet — point your apps at /api/v1/logs/ingest with an API key." /> : null}
      {logs.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Level</th>
                <th>Application</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((entry: LogEntry) => (
                <tr key={entry.id}>
                  <td>{formatDate(entry.timestamp)}</td>
                  <td>
                    <span className={levelClass(entry.level)}>{entry.level}</span>
                  </td>
                  <td>
                    {entry.application}
                    {entry.environment ? <span className="field-hint"> · {entry.environment}</span> : null}
                  </td>
                  <td>
                    <span className="cell-value">{entry.message}</span>
                    {entry.attributes && Object.keys(entry.attributes).length ? (
                      <details>
                        <summary>attributes</summary>
                        <pre className="log-attributes">{JSON.stringify(entry.attributes, null, 2)}</pre>
                      </details>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function ApiKeysPage({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const confirmAction = useConfirm();
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);
  const query = useQuery({
    queryKey: ["api-keys", organization?.public_id],
    queryFn: () => apiKeyService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const create = useMutation({
    mutationFn: () =>
      apiKeyService.create({
        organization_id: organization!.public_id,
        name,
        scopes: scopes as ApiKeyScope[],
      }),
    onSuccess: (key) => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      setCreatedKey(key);
      setName("");
      setScopes([]);
      notify("API key created — copy it now, it is shown only once.");
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => apiKeyService.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      notify("API key revoked.");
    },
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const keys = query.data?.api_keys ?? [];
  const scopeOptions: Array<{ value: NonNullable<ApiKey["scopes"]>[number]; label: string }> = [
    { value: "logs:write", label: "Log ingestion" },
    { value: "metrics:write", label: "Host metrics" },
    { value: "traces:write", label: "Trace ingestion" },
  ];

  return (
    <section>
      <PageHeader
        title="API keys"
        description="Machine credentials for log, metric, and trace ingestion. Keys are hashed — the raw value is shown once."
      />
      <form
        className="form-panel wide"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <div className="form-grid">
          <label>
            Key name
            <input value={name} onChange={(event) => setName(event.target.value)} required placeholder="e.g. checkout-api agent" />
          </label>
        </div>
        <fieldset className="field-group">
          <legend>Scopes (none selected = full ingestion access)</legend>
          <div className="checkbox-grid">
            {scopeOptions.map((option) => (
              <label key={option.value} className="checkbox-item">
                <input
                  type="checkbox"
                  checked={scopes.includes(option.value)}
                  onChange={(event) => {
                    setScopes((current) =>
                      event.target.checked
                        ? [...current, option.value]
                        : current.filter((scope) => scope !== option.value),
                    );
                  }}
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
        {create.isError ? <p className="error-text">{unwrapError(create.error)}</p> : null}
        <button className="button primary" disabled={create.isPending}>
          Create API key
        </button>
      </form>
      {createdKey ? (
        <section className="panel success-panel">
          <h2>Copy your API key now</h2>
          <p className="field-hint">
            This is the only time the full key is shown. Only the prefix <code>{createdKey.key_prefix}</code> is stored.
          </p>
          <code className="raw-key">{createdKey.key}</code>
          <button
            className="button secondary"
            onClick={() => {
              navigator.clipboard.writeText(createdKey.key);
              notify("API key copied to clipboard.");
            }}
          >
            <Copy size={16} />
            Copy key
          </button>
        </section>
      ) : null}
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {revoke.isError ? <ErrorBox message={unwrapError(revoke.error)} /> : null}
      {!query.isLoading && !keys.length ? <EmptyInline text="No API keys yet." /> : null}
      {keys.length ? (
        <DataTable
          headers={["Name", "Key", "Scopes", "Last used", "Status", ""]}
          rows={keys.map((key) => [
            key.name,
            <code>{key.key_prefix}…</code>,
            key.scopes?.length ? key.scopes.join(", ") : "all",
            formatDate(key.last_used_at),
            <span className={key.expires_at && new Date(key.expires_at) < new Date() ? "status bad" : "status ok"}>
              {key.expires_at && new Date(key.expires_at) < new Date() ? "EXPIRED" : "ACTIVE"}
            </span>,
            <div className="row-actions">
              <button
                className="button compact danger"
                disabled={revoke.isPending}
                onClick={() => {
                  confirmAction({
                    title: `Revoke API key "${key.name}"?`,
                    message: "Clients using this key will immediately fail authentication.",
                  }).then((confirmed) => {
                    if (confirmed) {
                      revoke.mutate(key.id);
                    }
                  });
                }}
              >
                Revoke
              </button>
            </div>,
          ])}
        />
      ) : null}
    </section>
  );
}

function InfrastructurePage({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [thresholdHost, setThresholdHost] = useState<string | null>(null);
  const [cpu, setCpu] = useState("");
  const [memory, setMemory] = useState("");
  const [disk, setDisk] = useState("");
  const [processes, setProcesses] = useState("");
  const query = useQuery({
    queryKey: ["infra-hosts", organization?.public_id],
    queryFn: () => infrastructureService.hosts(organization!.public_id, 6),
    enabled: Boolean(organization),
    refetchInterval: 30000,
  });
  const saveThreshold = useMutation({
    mutationFn: (host: string) =>
      infrastructureService.createThreshold({
        organization_id: organization!.public_id,
        host,
        cpu_percent: cpu ? Number(cpu) : null,
        memory_percent: memory ? Number(memory) : null,
        disk_percent: disk ? Number(disk) : null,
        process_names: processes
          .split(",")
          .map((name) => name.trim())
          .filter(Boolean),
      }),
    onSuccess: (threshold) => {
      queryClient.invalidateQueries({ queryKey: ["infra-hosts"] });
      notify(`Thresholds saved for ${threshold.host}.`);
      setThresholdHost(null);
    },
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const hosts = query.data?.hosts ?? [];
  const usage = (value: number | null | undefined) => (value == null ? "—" : `${Math.round(value)}%`);
  const barTone = (value: number | null, limit: number) => {
    if (value == null) return "";
    if (value > limit) return "bad";
    if (value >= limit * 0.9) return "warn";
    return "ok";
  };

  return (
    <section>
      <PageHeader
        title="Infrastructure"
        description="Hosts reporting through the WATCHDOG agent. Run agent/watchdog_agent.py on any Linux host."
      />
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {saveThreshold.isError ? <ErrorBox message={unwrapError(saveThreshold.error)} /> : null}
      {!query.isLoading && !hosts.length ? (
        <EmptyInline text="No hosts reporting yet — install the agent and give it an API key." />
      ) : null}
      {hosts.map((host) => {
        const latest = host.latest;
        const cpuLimit = host.threshold?.cpu_percent ?? 90;
        const memLimit = host.threshold?.memory_percent ?? 90;
        const diskLimit = host.threshold?.disk_percent ?? 90;
        return (
          <div className="panel host-panel" key={host.host}>
            <div className="host-head">
              <h3>
                <Server size={18} /> {host.host}
                {host.environment ? <span className="field-hint"> · {host.environment}</span> : null}
              </h3>
              <span className={healthClass(host.health)}>{host.health}</span>
            </div>
            {latest ? (
              <>
                <div className="usage-row">
                  <span>CPU {usage(latest.cpu_percent)} / {cpuLimit}%</span>
                  <div className="usage-bar">
                    <div className={`usage-fill ${barTone(latest.cpu_percent, cpuLimit)}`} style={{ width: `${latest.cpu_percent ?? 0}%` }} />
                  </div>
                </div>
                <div className="usage-row">
                  <span>Memory {usage(latest.memory_percent)} / {memLimit}%</span>
                  <div className="usage-bar">
                    <div className={`usage-fill ${barTone(latest.memory_percent, memLimit)}`} style={{ width: `${latest.memory_percent ?? 0}%` }} />
                  </div>
                </div>
                <div className="usage-row">
                  <span>Disk {usage(latest.disk_percent)} / {diskLimit}%</span>
                  <div className="usage-bar">
                    <div className={`usage-fill ${barTone(latest.disk_percent, diskLimit)}`} style={{ width: `${latest.disk_percent ?? 0}%` }} />
                  </div>
                </div>
                <p className="field-hint">
                  Net in {latest.net_in_kb_per_s ?? 0} KB/s · out {latest.net_out_kb_per_s ?? 0} KB/s ·{" "}
                  {latest.disk_used_gb != null ? `${latest.disk_used_gb} GB used · ` : ""}
                  sampled {formatDate(latest.measured_at)}
                </p>
                {latest.service_checks && typeof latest.service_checks === "object" ? (
                  <p className="field-hint">
                    Services:{" "}
                    {Object.entries(latest.service_checks as Record<string, boolean>)
                      .map(([name, running]) => `${name}${running ? " ✓" : " ✗"}`)
                      .join(" · ") || "none watched"}
                  </p>
                ) : null}
              </>
            ) : (
              <EmptyInline text="No samples in the last 6 hours." />
            )}
            <div className="row-actions">
              <button
                className="button compact secondary"
                onClick={() => {
                  setThresholdHost(thresholdHost === host.host ? null : host.host);
                  setCpu(host.threshold?.cpu_percent != null ? String(host.threshold.cpu_percent) : "");
                  setMemory(host.threshold?.memory_percent != null ? String(host.threshold.memory_percent) : "");
                  setDisk(host.threshold?.disk_percent != null ? String(host.threshold.disk_percent) : "");
                  setProcesses((host.threshold?.process_names ?? []).join(", "));
                }}
              >
                <Pencil size={14} />
                {host.threshold ? "Edit thresholds" : "Set thresholds"}
              </button>
            </div>
            {thresholdHost === host.host ? (
              <form
                className="form-panel"
                onSubmit={(event) => {
                  event.preventDefault();
                  saveThreshold.mutate(host.host);
                }}
              >
                <div className="form-grid">
                  <label>
                    CPU %
                    <input type="number" min={1} max={100} value={cpu} onChange={(event) => setCpu(event.target.value)} />
                  </label>
                  <label>
                    Memory %
                    <input type="number" min={1} max={100} value={memory} onChange={(event) => setMemory(event.target.value)} />
                  </label>
                  <label>
                    Disk %
                    <input type="number" min={1} max={100} value={disk} onChange={(event) => setDisk(event.target.value)} />
                  </label>
                </div>
                <label>
                  Required services (comma-separated)
                  <input value={processes} onChange={(event) => setProcesses(event.target.value)} placeholder="nginx, postgres" />
                </label>
                <button className="button primary compact" disabled={saveThreshold.isPending}>
                  Save thresholds
                </button>
              </form>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}

function TracesPage({ organization }: { organization?: Organization }) {
  const [openTrace, setOpenTrace] = useState<string | null>(null);
  const [serviceFilter, setServiceFilter] = useState("");
  const traces = useQuery({
    queryKey: ["traces", organization?.public_id, serviceFilter],
    queryFn: () =>
      traceService.list({
        organizationId: organization!.public_id,
        service: serviceFilter || undefined,
        limit: 50,
      }),
    enabled: Boolean(organization),
  });
  const serviceMap = useQuery({
    queryKey: ["service-map", organization?.public_id],
    queryFn: () => traceService.serviceMap(organization!.public_id),
    enabled: Boolean(organization),
  });
  const detail = useQuery({
    queryKey: ["trace", openTrace, organization?.public_id],
    queryFn: () => traceService.get(openTrace!, organization!.public_id),
    enabled: Boolean(organization) && Boolean(openTrace),
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const traceList = traces.data?.traces ?? [];
  const edges = serviceMap.data?.edges ?? [];
  const spans = detail.data?.spans ?? [];
  const spanDepth = (span: TraceSpan, all: TraceSpan[]) => {
    let depth = 0;
    let current = span;
    while (current.parent_span_id && depth < 12) {
      const parent = all.find((candidate) => candidate.span_id === current.parent_span_id);
      if (!parent) break;
      current = parent;
      depth += 1;
    }
    return depth;
  };
  // Position each bar where the span actually started inside the trace window.
  const traceStartMs = spans.length
    ? Math.min(...spans.map((span) => new Date(span.start_time).getTime()))
    : 0;
  const traceEndMs = spans.length
    ? Math.max(
        ...spans.map((span) => new Date(span.end_time || span.start_time).getTime()),
      )
    : 1;
  const traceWindowMs = Math.max(1, traceEndMs - traceStartMs);

  return (
    <section>
      <PageHeader
        title="Traces"
        description="Distributed traces ingested in OTLP/JSON format, with a derived service dependency map."
      />
      <form
        className="filter-row"
        onSubmit={(event) => {
          event.preventDefault();
          traces.refetch();
        }}
      >
        <input
          placeholder="Filter by service…"
          value={serviceFilter}
          onChange={(event) => setServiceFilter(event.target.value)}
        />
        <button className="button secondary compact" type="submit">
          Apply
        </button>
      </form>
      {traces.isLoading ? <TableSkeleton /> : null}
      {traces.isError ? <ErrorBox message={unwrapError(traces.error)} /> : null}
      {detail.isError ? <ErrorBox message={unwrapError(detail.error)} /> : null}
      {!traces.isLoading && !traceList.length ? (
        <EmptyInline text="No traces yet — point an OpenTelemetry OTLP/JSON exporter at /api/v1/traces/ingest with an API key." />
      ) : null}
      {traceList.length ? (
        <DataTable
          headers={["Trace", "Root operation", "Spans", "Services", "Errors", "Duration", "Started", ""]}
          rows={traceList.map((trace) => [
            <code>{trace.trace_id.slice(0, 12)}…</code>,
            `${trace.root_service ?? "?"} · ${trace.root_operation ?? "?"}`,
            trace.span_count,
            trace.service_count,
            trace.error_count ? (
              <span className="status bad">{trace.error_count}</span>
            ) : (
              <span className="status ok">0</span>
            ),
            trace.duration_ms != null ? `${Math.round(trace.duration_ms)} ms` : "—",
            formatDate(trace.started_at),
            <div className="row-actions">
              <button
                className="button compact secondary"
                onClick={() => setOpenTrace(openTrace === trace.trace_id ? null : trace.trace_id)}
              >
                {openTrace === trace.trace_id ? "Hide waterfall" : "Waterfall"}
              </button>
            </div>,
          ])}
        />
      ) : null}
      {openTrace && spans.length ? (
        <div className="panel">
          <h3>Waterfall — {openTrace.slice(0, 12)}…</h3>
          <div className="waterfall">
            {spans.map((span: TraceSpan) => (
              <div className="waterfall-row" key={span.span_id} style={{ paddingLeft: spanDepth(span, spans) * 18 }}>
                <span className="waterfall-label">
                  {span.service} · {span.operation}
                </span>
                <div className="waterfall-track">
                  <div
                    className={`waterfall-bar ${span.status === "ERROR" ? "bad" : "ok"}`}
                    style={{
                      marginLeft: `${
                        ((new Date(span.start_time).getTime() - traceStartMs) / traceWindowMs) * 100
                      }%`,
                      width: `${Math.max(2, ((span.duration_ms ?? 0) / traceWindowMs) * 100)}%`,
                    }}
                    title={`${Math.round(span.duration_ms ?? 0)} ms`}
                  />
                </div>
                <span className="waterfall-ms">{span.duration_ms != null ? `${Math.round(span.duration_ms)} ms` : "—"}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {serviceMap.isError ? <ErrorBox message={unwrapError(serviceMap.error)} /> : null}
      {edges.length ? (
        <div className="panel">
          <h3>Service dependency map</h3>
          <DataTable
            headers={["From", "To", "Calls", "Avg duration", "Errors"]}
            rows={edges.map((edge: ServiceMapEdge) => [
              edge.source,
              edge.target,
              edge.call_count,
              edge.avg_duration_ms != null ? `${Math.round(edge.avg_duration_ms)} ms` : "—",
              edge.error_count || "0",
            ])}
          />
        </div>
      ) : null}
    </section>
  );
}

function SlosPage({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const confirmAction = useConfirm();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [monitorId, setMonitorId] = useState("");
  const [target, setTarget] = useState(99.9);
  const [windowDays, setWindowDays] = useState(30);
  const monitors = useQuery({
    queryKey: ["monitors", organization?.public_id],
    queryFn: () => monitorService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const query = useQuery({
    queryKey: ["slos", organization?.public_id],
    queryFn: () => sloService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const statuses = useQueries({
    queries: (query.data?.slos ?? []).map((slo) => ({
      queryKey: ["slo-status", slo.id],
      queryFn: () => sloService.status(slo.id),
      enabled: Boolean(organization),
    })),
  });
  const create = useMutation({
    mutationFn: () =>
      sloService.create({
        organization_id: organization!.public_id,
        monitor_id: monitorId,
        name,
        target_percentage: target,
        window_days: windowDays,
      }),
    onSuccess: (slo) => {
      queryClient.invalidateQueries({ queryKey: ["slos"] });
      notify(`SLO "${slo.name}" created.`);
      setShowForm(false);
      setName("");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => sloService.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["slos"] });
      notify("SLO deleted.");
    },
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const slos = query.data?.slos ?? [];

  return (
    <section>
      <PageHeader
        title="SLOs"
        description="Service level objectives with error-budget tracking, computed from check results."
      >
        <button className="button primary" onClick={() => setShowForm((open) => !open)}>
          <Plus size={16} />
          New SLO
        </button>
      </PageHeader>
      {showForm ? (
        <form
          className="form-panel wide"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <div className="form-grid">
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Monitor
              <select value={monitorId} onChange={(event) => setMonitorId(event.target.value)} required>
                <option value="">Select a monitor…</option>
                {(monitors.data?.monitors ?? []).map((monitor) => (
                  <option key={monitor.public_id} value={monitor.public_id}>
                    {monitor.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Target %
              <input
                type="number"
                min={50}
                max={100}
                step={0.01}
                value={target}
                onChange={(event) => setTarget(Number(event.target.value))}
              />
            </label>
            <label>
              Window (days)
              <input
                type="number"
                min={1}
                max={365}
                value={windowDays}
                onChange={(event) => setWindowDays(Number(event.target.value))}
              />
            </label>
          </div>
          {create.isError ? <p className="error-text">{unwrapError(create.error)}</p> : null}
          <button className="button primary" disabled={create.isPending}>
            Create SLO
          </button>
        </form>
      ) : null}
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {remove.isError ? <ErrorBox message={unwrapError(remove.error)} /> : null}
      {!query.isLoading && !slos.length ? <EmptyInline text="No SLOs defined yet." /> : null}
      {slos.map((slo: SLO, index: number) => {
        const status = statuses[index]?.data;
        const attained = status?.attained_percentage ?? null;
        const remaining = status?.error_budget_remaining_percentage ?? null;
        return (
          <div className="panel host-panel" key={slo.id}>
            <div className="host-head">
              <h3>
                <Target size={18} /> {slo.name}
                {status ? <span className="field-hint"> · {status.monitor_name}</span> : null}
              </h3>
              {status ? (
                <span className={status.target_met ? "status ok" : "status bad"}>
                  {status.target_met ? "MET" : "MISSED"}
                </span>
              ) : null}
            </div>
            <p className="field-hint">
              Target {slo.target_percentage}% over {slo.window_days} days
              {attained != null ? ` · attained ${attained.toFixed(2)}%` : ""}
              {status ? ` · ${status.total_checks} checks` : ""}
            </p>
            {remaining != null ? (
              <div className="usage-row">
                <span>Error budget remaining {remaining}%</span>
                <div className="usage-bar">
                  <div className={`usage-fill ${remaining > 25 ? "ok" : remaining > 0 ? "warn" : "bad"}`} style={{ width: `${remaining}%` }} />
                </div>
              </div>
            ) : null}
            <div className="row-actions">
              <button
                className="button compact danger"
                disabled={remove.isPending}
                onClick={() => {
                  confirmAction({
                    title: `Delete SLO "${slo.name}"?`,
                    message: "This only removes the objective — monitors and checks are unaffected.",
                  }).then((confirmed) => {
                    if (confirmed) {
                      remove.mutate(slo.id);
                    }
                  });
                }}
              >
                Delete
              </button>
            </div>
          </div>
        );
      })}
    </section>
  );
}

const WIDGET_TYPES = [
  "monitor_status",
  "uptime",
  "response_times",
  "log_volume",
  "host_health",
  "incidents",
  "service_map",
  "slo_status",
] as const;

function DashboardsPage({ organization }: { organization?: Organization }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const confirmAction = useConfirm();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [widgets, setWidgets] = useState<Array<{ type: (typeof WIDGET_TYPES)[number]; title: string }>>([
    { type: "monitor_status", title: "Services" },
  ]);
  const query = useQuery({
    queryKey: ["dashboards", organization?.public_id],
    queryFn: () => dashboardTemplateService.list(organization!.public_id),
    enabled: Boolean(organization),
  });
  const create = useMutation({
    mutationFn: () =>
      dashboardTemplateService.create({
        organization_id: organization!.public_id,
        name,
        description: description || null,
        is_default: false,
        widgets: widgets.map((widget) => ({ ...widget, config: {} })),
      }),
    onSuccess: (dashboard) => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
      notify(`Dashboard "${dashboard.name}" created.`);
      setShowForm(false);
      setName("");
      setDescription("");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => dashboardTemplateService.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
      notify("Dashboard deleted.");
    },
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const dashboards = query.data?.dashboards ?? [];

  return (
    <section>
      <PageHeader
        title="Dashboards"
        description="Reusable dashboard layouts composed of widgets — build once per client or team."
      >
        <button className="button primary" onClick={() => setShowForm((open) => !open)}>
          <Plus size={16} />
          New dashboard
        </button>
      </PageHeader>
      {showForm ? (
        <form
          className="form-panel wide"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <div className="form-grid">
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Description
              <input value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
          </div>
          <fieldset className="field-group">
            <legend>Widgets</legend>
            {widgets.map((widget, index) => (
              <div className="widget-row" key={index}>
                <select
                  value={widget.type}
                  onChange={(event) => {
                    setWidgets((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, type: event.target.value as (typeof WIDGET_TYPES)[number] } : item,
                      ),
                    );
                  }}
                >
                  {WIDGET_TYPES.map((option) => (
                    <option key={option} value={option}>
                      {option.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
                <input
                  value={widget.title}
                  placeholder="Widget title"
                  onChange={(event) => {
                    setWidgets((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, title: event.target.value } : item,
                      ),
                    );
                  }}
                />
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Remove widget"
                  onClick={() => setWidgets((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                >
                  <X size={16} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="button compact secondary"
              onClick={() => setWidgets((current) => [...current, { type: "uptime", title: "Uptime" }])}
            >
              <Plus size={14} />
              Add widget
            </button>
          </fieldset>
          {create.isError ? <p className="error-text">{unwrapError(create.error)}</p> : null}
          <button className="button primary" disabled={create.isPending}>
            Create dashboard
          </button>
        </form>
      ) : null}
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {remove.isError ? <ErrorBox message={unwrapError(remove.error)} /> : null}
      {!query.isLoading && !dashboards.length ? <EmptyInline text="No dashboards yet." /> : null}
      {dashboards.length ? (
        <DataTable
          headers={["Name", "Description", "Widgets", "Default", "Created", ""]}
          rows={dashboards.map((dashboard: DashboardTemplate) => [
            dashboard.name,
            dashboard.description ?? "—",
            (dashboard.widgets ?? []).map((widget) => widget.type.replaceAll("_", " ")).join(", ") || "—",
            dashboard.is_default ? <span className="status ok">DEFAULT</span> : "—",
            formatDate(dashboard.created_at),
            <div className="row-actions">
              <button
                className="icon-button"
                title="Delete dashboard"
                aria-label={`Delete dashboard ${dashboard.name}`}
                disabled={remove.isPending}
                onClick={() => {
                  confirmAction({
                    title: `Delete dashboard "${dashboard.name}"?`,
                    message: "The template layout will be removed.",
                  }).then((confirmed) => {
                    if (confirmed) {
                      remove.mutate(dashboard.id);
                    }
                  });
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

function HealthPage({ organization }: { organization?: Organization }) {
  const query = useQuery({
    queryKey: ["service-health", organization?.public_id],
    queryFn: () => analyticsService.serviceHealth(organization!.public_id),
    enabled: Boolean(organization),
    refetchInterval: 30000,
  });
  if (!organization) {
    return <EmptyOrganizations />;
  }
  const health = query.data;
  const services = health?.services ?? [];
  const counts = health?.counts;

  return (
    <section>
      <PageHeader
        title="Service health"
        description="One view across every monitor: status, 24h uptime and latency, maintenance state, and SSL headroom."
      />
      {query.isLoading ? <SkeletonGrid /> : null}
      {query.isError ? <ErrorBox message={unwrapError(query.error)} /> : null}
      {counts ? (
        <div className="metric-grid">
          <Metric label="Up" value={counts.UP} icon={CheckCircle2} tone="ok" />
          <Metric label="Down" value={counts.DOWN} icon={AlertTriangle} tone={counts.DOWN ? "bad" : "ok"} />
          <Metric label="Degraded" value={counts.DEGRADED} icon={Gauge} tone={counts.DEGRADED ? "warn" : "ok"} />
          <Metric label="In maintenance" value={counts.MAINTENANCE} icon={Wrench} />
        </div>
      ) : null}
      {!query.isLoading && !services.length ? <EmptyInline text="No monitors yet." /> : null}
      {services.length ? (
        <DataTable
          headers={["Service", "Type", "Status", "Uptime 24h", "Latency 24h", "Client", "Environment", "Tags", "SSL", "Last checked"]}
          rows={services.map((service) => [
            <Link to={`/app/monitors/${service.public_id}`}>{service.name}</Link>,
            service.monitor_type,
            <span className={service.in_maintenance ? "status" : statusClass(service.status)}>
              {service.in_maintenance ? "MAINTENANCE" : service.status}
            </span>,
            service.uptime_24h != null ? `${service.uptime_24h}%` : "—",
            service.avg_latency_24h != null ? `${Math.round(service.avg_latency_24h)} ms` : "—",
            service.client_name ?? "—",
            service.environment ?? "—",
            service.tags?.length ? service.tags.join(", ") : "—",
            service.ssl_days_remaining != null
              ? service.ssl_days_remaining <= 0
                ? <span className="status bad">EXPIRED</span>
                : service.ssl_days_remaining < 14
                  ? <span className="status warn">{Math.round(service.ssl_days_remaining)}d</span>
                  : `${Math.round(service.ssl_days_remaining)}d`
              : "—",
            formatDate(service.last_checked_at),
          ])}
        />
      ) : null}
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

function ToastStack({
  toasts,
  dismiss,
}: {
  toasts: ToastMessage[];
  dismiss: (id: number) => void;
}) {
  if (!toasts.length) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <button
          key={toast.id}
          className={`toast ${toast.tone}`}
          type="button"
          onClick={() => dismiss(toast.id)}
          title="Dismiss message"
        >
          {toast.tone === "success" ? <CheckCircle2 size={18} /> : <Bell size={18} />}
          <span>{toast.message}</span>
          <X size={15} />
        </button>
      ))}
    </div>
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
    <NotificationProvider>
      <ConfirmProvider>
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
      </ConfirmProvider>
    </NotificationProvider>
  );
}
