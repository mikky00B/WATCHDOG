# WATCHDOG

Uptime, log, and infrastructure monitoring for agencies and development teams.

WATCHDOG watches your websites, APIs, SSL certificates, DNS records, TCP ports, and cron jobs — opens incidents when things break, alerts you through email and Telegram, publishes public status pages, ingests application logs and host metrics, and tracks SLOs. Built with FastAPI, PostgreSQL, and React.

**What it does**

- **Monitors** — HTTP checks with status/keyword/JSON/header/response-time assertions, SSL certificate expiry, DNS record resolution, TCP port connectivity, and heartbeat push check-ins for cron jobs. Checks run on an in-process scheduler with retries, rate limiting, and SSRF protection.
- **Incidents & alerts** — failures above a threshold open incidents with an acknowledge/resolve trail; alerts fan out through email, Telegram, and webhook channels with cooldown deduplication. Threshold, error-rate, uptime, latency-anomaly, and SSL-expiry rules run automatically.
- **Maintenance windows** — scheduled windows pause checks, incidents, and heartbeat misses for covered monitors, and appear on public status pages.
- **Log management** — applications ship structured logs to an authenticated ingestion API; secrets are redacted before storage, logs are searchable, and volume/error charts are served for dashboards. Retention is automatic.
- **Infrastructure monitoring** — a lightweight Linux agent (`agent/`) reports CPU, memory, disk, network, processes, and service status; per-host thresholds raise deduplicated alerts.
- **Tracing** — accepts OTLP/JSON spans from OpenTelemetry SDKs; browse traces as span waterfalls and derive a service dependency map.
- **SLOs** — error-budget tracking per monitor computed from check results.
- **Dashboards & reports** — reusable widget dashboards, historical latency/uptime charts, service health overview, correlated incident timelines, and monthly client reliability reports.

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2 (async), PostgreSQL (asyncpg), Alembic, httpx, structlog, dnspython
- **Frontend:** React 19, TypeScript, Vite, TanStack Query, React Router, Recharts
- **Agent:** Python 3.8+ with psutil only

## Quick Start

Prerequisites: Python 3.11+, Node.js 20+, npm, PostgreSQL.

### Backend

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
Copy-Item .env.example .env
```

Set your database URL in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/monitoring
```

Create the schema and start the API:

```powershell
python -m alembic upgrade head
uvicorn monitoring.main:app --host 127.0.0.1 --port 8000 --reload
```

Alembic is the only schema bootstrap path — a fresh database must be fully created by `alembic upgrade head`; the app does not rely on `create_all()`.

The API process also starts the monitor scheduler and notification worker, so no separate worker is needed for local development.

| URL | |
|---|---|
| API | http://127.0.0.1:8000 |
| Swagger docs | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/health |

### Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Dashboard: http://127.0.0.1:5173

`frontend/.env` should contain:

```env
VITE_API_BASE_URL=/api/v1
VITE_APP_NAME=WATCHDOG
```

The Vite dev server proxies `/api` to the backend.

### First run

1. Register at `/register` and verify your email with the six-digit code.
2. Create an organization — this is your workspace.
3. Add monitors (website, API, SSL, DNS, TCP, or heartbeat) with environments and tags.
4. Add an alert channel (email or Telegram) so failures reach you.
5. Create an API key under **API Keys** — it authenticates log, metric, and trace ingestion.
6. Optional: add clients (per-customer grouping), a status page, SLOs, and maintenance windows.

## Configuration

Key `.env` values (see `.env.example` for the full set):

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/monitoring
ENVIRONMENT=development
JWT_SECRET_KEY=change-this-to-a-long-random-secret

CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]

DEFAULT_CHECK_INTERVAL=60
MAX_CONCURRENT_CHECKS=100
REQUESTS_PER_MINUTE_PER_SITE=10
RUN_SCHEDULER_IN_API=true

EMAIL_ENABLED=true
RESEND_API_KEY=re_your_resend_api_key
FROM_EMAIL=alerts@yourdomain.com

TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_ALLOWED_CHAT_IDS=123456789

LOG_LEVEL=INFO
LOG_RETENTION_DAYS=30
HOST_METRIC_RETENTION_DAYS=14
TRACE_RETENTION_DAYS=7
```

Notes:

- Email is sent through Resend's HTTP API. `RESENT_API_KEY` is also accepted as a legacy alias. `FROM_EMAIL` must be a Resend-verified sender. Alert recipients come from alert channels, not from `.env`.
- `ENVIRONMENT=production` refuses the default development `JWT_SECRET_KEY` — set a long random secret before deploying, and keep `AUTO_CREATE_TABLES=false` (run `alembic upgrade head` during deployment instead).
- The retention variables control how long ingested logs, host metrics, and trace spans are kept; the scheduler purges expired rows automatically.

## Usage

### Authentication

```bash
# Register (then verify the emailed six-digit code)
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"test@example.com","password":"StrongPass123"}'

# Log in -> access_token + refresh_token
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"StrongPass123"}'

# Refresh / logout / password reset
POST /api/v1/auth/refresh     {"refresh_token": "..."}
POST /api/v1/auth/logout      {"refresh_token": "..."}
POST /api/v1/auth/forgot-password  {"email": "..."}
POST /api/v1/auth/reset-password   {"email": "...", "code": "123456", "new_password": "..."}
```

All protected endpoints take `Authorization: Bearer YOUR_ACCESS_TOKEN`. Interactive docs for every endpoint are at `/docs`.

### Monitors

```bash
# Organization
curl -X POST http://127.0.0.1:8000/api/v1/organizations/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Demo Agency","slug":"demo-agency"}'

# Website monitor with environment and tags
curl -X POST http://127.0.0.1:8000/api/v1/monitors/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Website","url":"https://example.com","monitor_type":"WEBSITE","interval_seconds":60,"environment":"production","tags":["client-acme"]}'

# SSL certificate monitor - warns when expiry is within ssl_expiry_threshold_days
curl -X POST http://127.0.0.1:8000/api/v1/monitors/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Client SSL","monitor_type":"SSL","url":"https://clientwebsite.com","interval_seconds":86400,"ssl_expiry_threshold_days":14}'

# TCP port monitor
curl -X POST http://127.0.0.1:8000/api/v1/monitors/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Postgres","monitor_type":"TCP","url":"tcp://db.example.com","port":5432,"interval_seconds":60}'

# Heartbeat monitor - create response includes heartbeat_url to ping from your cron job
curl -X POST http://127.0.0.1:8000/api/v1/monitors/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Nightly backup","monitor_type":"HEARTBEAT","interval_seconds":3600}'

# Run a check now / list check history / per-monitor stats
POST /api/v1/monitors/{id}/run-check
GET  /api/v1/monitors/{id}/checks
GET  /api/v1/monitors/{id}/stats

# Filter the monitor list
GET /api/v1/monitors/?organization_id=...&monitor_type=SSL&status=UP&environment=production&tag=critical
```

Heartbeat check-ins: `POST /api/v1/monitors/heartbeat/{heartbeat_key}`. Missed heartbeats are detected by the scheduler and open incidents like any other failure. The older `/api/v1/heartbeats` standalone API is deprecated and kept only for legacy clients.

API monitors support `expected_status_code`, `expected_response_text` (keyword), `expected_json` (nested dot-paths like `data.status`), `expected_headers`, and `response_time_threshold_ms`.

### Maintenance windows

Windows suppress scheduled checks, incident creation, and missed-heartbeat detection for their monitors while active, and show up on public status pages:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/maintenance-windows/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","title":"DB upgrade","starts_at":"2026-05-22T01:00:00Z","ends_at":"2026-05-22T03:00:00Z","monitor_ids":["MONITOR_PUBLIC_ID"]}'
```

### Alerts

When a failure opens an incident, active alert channels receive queued notification events; the notification worker delivers them and marks them `SENT` or `FAILED`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/alert-channels/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"organization_id":1,"name":"Ops Email","channel_type":"EMAIL","config":{"email":"ops@example.com"}}'
```

Supported channel types: `EMAIL`, `TELEGRAM`, `WEBHOOK`. Test a channel with `POST /api/v1/alert-channels/{id}/test`.

### Telegram bot

Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_URL`, and `TELEGRAM_ALLOWED_CHAT_IDS`, then register the webhook:

```powershell
python scripts/register_telegram_webhook.py
```

Bot commands: `/status`, `/monitors`, `/alerts`, `/ack <alert_id>`, `/resolve <alert_id>`, `/enable <monitor_id>`, `/disable <monitor_id>`.

### Status pages

```bash
curl http://127.0.0.1:8000/api/v1/public/status-pages/STATUS_PAGE_SLUG
```

Public route in the dashboard: `/status/:slug`. Shows per-service status, uptime, active/recent incidents, and maintenance windows.

### Reports

```bash
curl "http://127.0.0.1:8000/api/v1/reports/monthly?organization_id=ORG_PUBLIC_ID&year=2026&month=5" \
  -H "Authorization: Bearer $TOKEN"
```

HTML version at `GET /api/v1/reports/monthly/html`. Reports include per-monitor uptime, total downtime, incident counts, and average response time, scoped to a client or the whole organization. Generated on demand.

## Sending Data to WATCHDOG

All ingestion endpoints authenticate with an **API key** (`X-API-Key: wd_live_...`) created under **API Keys** in the dashboard. Keys are shown once, stored hashed, optionally scoped (`logs:write`, `metrics:write`, `traces:write`), and revocable.

### Application logs

```bash
curl -X POST http://127.0.0.1:8000/api/v1/logs/ingest \
  -H "Content-Type: application/json" -H "X-API-Key: wd_live_..." \
  -d '{"logs":[{"application":"checkout-api","level":"ERROR","message":"payment declined"}]}'
```

Batches up to 500 entries; levels are normalized (`warn` → `WARNING`, `fatal` → `CRITICAL`). Secret material — bearer/JWT tokens, `password:` style values, card-like numbers, sensitive attribute keys — is redacted at ingestion time and never stored. Query with JWT auth via `GET /api/v1/logs/` (application, level, environment, free-text search, trace-id, time-range filters) and `GET /api/v1/logs/stats` for volume and error-frequency chart data.

### Infrastructure agent

On any Linux host ([agent/README.md](agent/README.md)):

```bash
pip install psutil
python agent/watchdog_agent.py \
  --api-url http://watchdog-host:8000/api/v1 \
  --api-key wd_live_... \
  --interval 60 \
  --watch nginx,postgres
```

The agent reports CPU, memory, disk, network utilization, top processes, and whether watched services are running. Configure per-host thresholds (CPU/memory/disk %, required services) via `/api/v1/infrastructure/thresholds` or the Infrastructure page; the scheduler evaluates them periodically and raises deduplicated alerts through your channels. View hosts on the Infrastructure page or `GET /api/v1/infrastructure/hosts`.

### Traces (OpenTelemetry)

Point an OpenTelemetry SDK's OTLP/JSON exporter at:

```text
POST /api/v1/traces/ingest    (X-API-Key auth, traces:write scope)
```

The endpoint accepts standard `resourceSpans` OTLP/JSON payloads. Query traces, span waterfalls, and the dependency map:

```text
GET /api/v1/traces/?organization_id=&period=24h
GET /api/v1/traces/{trace_id}?organization_id=
GET /api/v1/traces/service-map?organization_id=&period=24h
```

## SLOs, Dashboards, and Analytics

```bash
# Define an SLO: target % over a rolling window of days
curl -X POST http://127.0.0.1:8000/api/v1/slos/ \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","monitor_id":"MONITOR_PUBLIC_ID","name":"API 99.9","target_percentage":99.9,"window_days":30}'

# Attainment and error budget
GET /api/v1/slos/{slo_id}/status
```

Analytics endpoints power the dashboards:

```text
GET /api/v1/analytics/response-times?organization_id=&period=24h   # avg/p95 latency buckets
GET /api/v1/analytics/uptime?organization_id=&period=7d            # uptime buckets
GET /api/v1/analytics/service-health?organization_id=              # per-monitor overview
GET /api/v1/analytics/incidents/{id}/timeline                      # correlated timeline
```

Incident timelines merge updates, alerts, failed checks, and application log errors from the incident window into one chronological view. Dashboard templates (`/api/v1/dashboards`) compose widgets — monitor status, uptime, response times, log volume, host health, incidents, service map, SLO status — into reusable layouts.

## Testing

```powershell
# Backend suite (coverage gate skipped for local runs)
python -m pytest --no-cov

# Frontend build
cd frontend
npm run build
```

Focused test files live under `tests/unit/` and `tests/integration/test_api/` — pick any with `python -m pytest tests/integration/test_api/test_observability_api.py --no-cov`.

Verify migrations against a fresh database (uses a disposable database — do not point it at real data):

```powershell
$env:WATCHDOG_MIGRATION_TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/watchdog_migration_test"
python scripts/verify_fresh_migrations.py
```

An end-to-end smoke script (`scripts/e2e_smoke_test.py`) exercises registration → organization → API key → ingestion → queries against a running server.

## Project Structure

```text
├── frontend/                # React + Vite dashboard (pages in src/ui/App.tsx)
├── src/monitoring/          # FastAPI application package
│   ├── api/v1/              # REST routes: auth, organizations, clients, monitors,
│   │                        # checks, alerts, alert-channels, incidents,
│   │                        # status-pages, reports, maintenance-windows,
│   │                        # api-keys, logs, infrastructure, traces, slos,
│   │                        # dashboards, analytics, telegram integration
│   ├── alerting/            # Email, Telegram, webhook senders
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic (checker, rule engine, incidents,
│   │                        # logs, traces, infrastructure, analytics, SLOs)
│   ├── core/                # Password hashing and token helpers
│   ├── utils/               # Logging, URL safety (SSRF), redaction
│   └── workers/             # Scheduler (checks + housekeeping), notification worker
├── agent/                   # Standalone Linux infrastructure agent
├── alembic/                 # Migrations
├── tests/                   # Unit and integration tests (SQLite in-memory)
├── scripts/                 # Utility and verification scripts
└── requirements.txt
```

## Troubleshooting

**Frontend cannot connect to the backend** — confirm both servers are running, `frontend/.env` has `VITE_API_BASE_URL=/api/v1`, `frontend/vite.config.ts` proxies `/api` to `http://127.0.0.1:8000`, and backend `CORS_ORIGINS` includes the frontend origin.

**Verification email not sent** — check `EMAIL_ENABLED=true`, `RESEND_API_KEY` is set, `FROM_EMAIL` is verified in Resend, and restart the backend after changing `.env`.

**Monitor URL blocked as unsafe** — WATCHDOG rejects localhost, private/internal IPs (after DNS resolution), and cloud metadata endpoints to prevent SSRF. Use public, resolvable targets for website/API monitors.

**Missing database columns** — run `python -m alembic upgrade head`.

## License

[MIT](LICENSE)
