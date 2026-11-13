# WATCHDOG Monitoring Platform

WATCHDOG is a FastAPI and React monitoring platform for agencies and teams that need uptime checks (HTTP, SSL certificates, DNS records, TCP ports), heartbeat checks, incidents, maintenance windows, client grouping, alert channels, status pages, monthly reliability reports, centralized log ingestion, infrastructure metrics from a lightweight agent, distributed traces (OTLP/JSON), SLO tracking, and reusable dashboards.


## Requirements

- Python 3.11+
- Node.js 20+
- npm
- PostgreSQL

## Backend Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
Copy-Item .env.example .env
```

Set your local database URL in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/monitoring
```

Apply migrations:

```powershell
python -m alembic upgrade head
```

Alembic is the schema bootstrap path for every environment. A fresh PostgreSQL
database must be fully created by `python -m alembic upgrade head`; production
does not rely on `Base.metadata.create_all()`.

Start the API:

```powershell
uvicorn monitoring.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend URLs:

- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

The API process starts both the monitor scheduler and notification worker. You do not need to start a separate worker for local development.

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Frontend URL:

- http://127.0.0.1:5173

The frontend uses Vite with a local proxy. `frontend/.env` should contain:

```env
VITE_API_BASE_URL=/api/v1
VITE_APP_NAME=WATCHDOG
```

If Vite fails with `spawn EPERM` on Windows, start the dev server from a normal terminal outside restricted tooling:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## Environment Configuration

Common backend `.env` values:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/monitoring
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development
AUTO_CREATE_TABLES=false
JWT_SECRET_KEY=change-this-to-a-long-random-secret

CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173","http://localhost:8000","http://127.0.0.1:8000"]

DEFAULT_CHECK_INTERVAL=60
DEFAULT_TIMEOUT=5.0
MAX_CONCURRENT_CHECKS=100
REQUESTS_PER_MINUTE_PER_SITE=10
MAX_CHECK_RETRIES=2
RUN_SCHEDULER_IN_API=true

EMAIL_ENABLED=true
RESENT_API_KEY=re_your_resend_api_key
FROM_EMAIL=michael@example.com
FROM_NAME="Michael from Watchdog"

TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_WEBHOOK_SECRET=your-random-webhook-secret
TELEGRAM_WEBHOOK_URL=https://your-domain.com/api/v1/integrations/telegram/webhook
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321

LOG_LEVEL=INFO
# Retention (days) for ingested observability data — purged by the scheduler
LOG_RETENTION_DAYS=30
HOST_METRIC_RETENTION_DAYS=14
TRACE_RETENTION_DAYS=7
```

Email notes:

- WATCHDOG sends email through Resend's HTTP API.
- `RESENT_API_KEY` is supported because it is the current project env name. `RESEND_API_KEY` also works.
- `FROM_EMAIL` must be a Resend-verified sender/domain.
- Verification and password-reset emails use a transactional template, not the monitor-alert template.
- Alert recipients come from Alert Channels, not from `.env`.

Production auth note:

- `ENVIRONMENT=production` refuses the default development `JWT_SECRET_KEY`.
- Use a long random secret before deploying.
- Keep `AUTO_CREATE_TABLES=false` in production. Run `python -m alembic upgrade head`
  during deployment before starting or restarting the API.

Development database note:

- Local development should also use `python -m alembic upgrade head`.
- `AUTO_CREATE_TABLES=true` is only a temporary local convenience for throwaway
  databases; do not use it for production or shared environments.

## Main User Flow

1. Register a user.
2. Enter the six-digit email verification code.
3. Log in after verification.
4. Create an organization.
5. Create clients if you manage monitors per client.
6. Create monitors (WEBSITE, API, SSL, DNS, TCP, HEARTBEAT) with environments and tags.
7. Add alert channels for the organization.
8. Create an API key for machine ingestion (logs, host metrics, traces).
9. Schedule maintenance windows to pause checks deliberately.
10. Create a status page and add monitor services.
11. Use Reports to generate monthly reliability summaries.
12. Track reliability with SLOs and error budgets; explore logs, traces, and hosts.

## Planned Product Additions

Implemented in the observability expansion (see `PROGRESS_CHECKLIST.md`):

- SSL/DNS/TCP monitoring, maintenance windows, monitor tags and environments
- Centralized log ingestion with redaction, search, and retention
- Infrastructure agent with CPU/memory/disk/network metrics and thresholds
- Distributed tracing (OTLP/JSON), service maps, SLOs, dashboards

Next up (from `Newplan.md`):

- Team management: organization invites, member roles (ADMIN/DEVELOPER/VIEWER/CLIENT),
  permission enforcement, audit logs
- Report features: scheduled monthly client report emails, persisted report
  history, PDF export
- SaaS monetization: subscription plans, usage limits, Paystack/Flutterwave and
  Stripe
- Remaining advanced checks: domain expiry, ICMP ping, multi-region checks
- Architecture hardening: persist alert cooldowns/rule registry to the database,
  SQL-side log bucketing, OTLP gRPC/protobuf support

## Auth Flow

Registration:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"test@example.com","password":"StrongPass123"}'
```

Verify email:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/verify-email \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","code":"123456"}'
```

Login:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"StrongPass123"}'
```

Refresh access token:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
```

Logout:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
```

Password reset:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'

curl -X POST http://127.0.0.1:8000/api/v1/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","code":"123456","new_password":"NewStrongPass123"}'
```

## Monitoring API Examples

Create an organization:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/organizations/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"name":"Demo Agency","slug":"demo-agency"}'
```

Create a website monitor:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/monitors/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Website","url":"https://example.com","monitor_type":"WEBSITE","interval_seconds":60,"environment":"production","tags":["client-acme"]}'
```

Create a TCP port monitor:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/monitors/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Postgres","monitor_type":"TCP","url":"tcp://db.example.com","port":5432,"interval_seconds":60}'
```

Run a manual check:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/monitors/MONITOR_PUBLIC_ID/run-check \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Get check history:

```bash
curl http://127.0.0.1:8000/api/v1/monitors/MONITOR_PUBLIC_ID/checks \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Alert Channels

Create an email alert channel:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/alert-channels/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"organization_id":1,"name":"Ops Email","channel_type":"EMAIL","config":{"email":"ops@example.com"}}'
```

Create a Telegram alert channel:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/alert-channels/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"organization_id":1,"name":"Ops Telegram","channel_type":"TELEGRAM","config":{"chat_id":"123456789"}}'
```

When a monitor failure creates an incident, active alert channels for that organization receive queued notification events. The notification worker sends pending events and marks them `SENT` or `FAILED`.

## Reports

The Reports tab generates server-calculated monthly reliability reports. It includes:

- Client or all-client scope
- Reporting period
- Monitors included
- Uptime percentage
- Total downtime
- Incident count
- Average response time
- Per-monitor summaries
- Incident list
- Authenticated HTML report view

Reports are generated on demand and are not persisted yet.

Planned report additions:

- Persist generated monthly reports
- Email scheduled monthly client reports
- Export monthly reports as PDF

JSON report endpoint:

```bash
curl "http://127.0.0.1:8000/api/v1/reports/monthly?organization_id=ORG_PUBLIC_ID&year=2026&month=5" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

HTML report endpoint:

```text
GET /api/v1/reports/monthly/html?organization_id=ORG_PUBLIC_ID&year=2026&month=5
```

## Status Pages

Public status pages are available without authentication:

```bash
curl http://127.0.0.1:8000/api/v1/public/status-pages/STATUS_PAGE_SLUG
```

Frontend public route:

```text
/status/:slug
```

## Heartbeats

The primary WATCHDOG heartbeat product path is a heartbeat-type monitor:

```json
{
  "organization_id": "ORG_PUBLIC_ID",
  "name": "Nightly backup",
  "monitor_type": "HEARTBEAT",
  "interval_seconds": 3600
}
```

The create response includes `heartbeat_url`, which should be called by the job
or worker being monitored. Missed heartbeat detection, incidents, alerting, and
status pages are all driven by these `Monitor` records.

The older `/api/v1/heartbeats` standalone API is deprecated and retained only
for legacy clients. Standalone heartbeat rows do not create incidents, send
alerts, or appear on status pages.

## Telegram Integration

Telegram uses webhook mode.

Configure:

```env
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_WEBHOOK_SECRET=your-random-webhook-secret
TELEGRAM_WEBHOOK_URL=https://your-domain.com/api/v1/integrations/telegram/webhook
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
```

Register the webhook:

```powershell
python scripts/register_telegram_webhook.py
```

Webhook route:

```text
/api/v1/integrations/telegram/webhook
```

Supported bot commands:

- `/status`
- `/monitors`
- `/alerts`
- `/ack <alert_id>`
- `/resolve <alert_id>`
- `/enable <monitor_id>`
- `/disable <monitor_id>`

## Testing

Run backend tests without the coverage gate while developing:

```powershell
python -m pytest --no-cov
```

Focused checks:

```powershell
python -m pytest tests\integration\test_api\test_auth_organizations_api.py --no-cov
python -m pytest tests\integration\test_api\test_monitors_api.py --no-cov
python -m pytest tests\integration\test_api\test_incidents_api.py --no-cov
python -m pytest tests\integration\test_api\test_alert_channels_api.py --no-cov
python -m pytest tests\integration\test_api\test_clients_status_pages_api.py --no-cov
python -m pytest tests\integration\test_api\test_reports_api.py --no-cov
python -m pytest tests\integration\test_api\test_observability_api.py --no-cov
python -m pytest tests\unit\test_services\test_checker_types.py --no-cov
python -m pytest tests\unit\test_services\test_observability_services.py --no-cov
python -m pytest tests\unit\test_services\test_rule_engine_new_rules.py --no-cov
python -m pytest tests\unit\test_schemas\test_monitor_new_types.py --no-cov
python -m pytest tests\unit\test_utils\test_redaction_time_period.py --no-cov
```

End-to-end smoke test (boots against a live API on a disposable database —
see the script header for setup):

```powershell
python scripts/e2e_smoke_test.py
```

Frontend build:

```powershell
cd frontend
npm run build
```

Fresh PostgreSQL migration verification:

```powershell
$env:WATCHDOG_MIGRATION_TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/watchdog_migration_test"
python scripts/verify_fresh_migrations.py
```

The script drops and recreates the `public` schema in the configured database,
then runs `alembic upgrade head`. Use only a disposable database. The equivalent
pytest test is skipped unless `WATCHDOG_MIGRATION_TEST_DATABASE_URL` is set.

## Project Structure

```text
monitoring-platform/
├── frontend/                # React + Vite dashboard
├── src/monitoring/          # FastAPI application package
│   ├── alerting/            # Email, Telegram, webhook, transactional email
│   ├── api/v1/              # REST routes (monitors, incidents, logs, traces,
│   │                        # infrastructure, slos, dashboards, analytics,
│   │                        # maintenance-windows, api-keys, ...)
│   ├── core/                # Password hashing and token helpers
│   ├── models/              # SQLAlchemy models (incl. LogEntry, TraceSpan,
│   │                        # HostMetric, HostThreshold, ApiKey, SLO,
│   │                        # MaintenanceWindow, DashboardTemplate)
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic (checker, rules, logs, traces,
│   │                        # infrastructure, analytics, SLOs, ...)
│   ├── utils/               # Logging, URL safety, redaction, period parsing
│   └── workers/             # Scheduler (checks + housekeeping) and
│                            # notification worker
├── agent/                   # Lightweight Linux infrastructure agent
├── alembic/                 # Database migrations
├── tests/                   # Unit and integration tests
├── scripts/                 # Utility scripts (incl. e2e_smoke_test.py)
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Monitoring Beyond HTTP

Monitor types: `WEBSITE`, `API` (HTTP with status/keyword/JSON/header/response-time assertions), `HEARTBEAT` (push check-ins), `SSL` (certificate expiry with DEGRADED warnings before expiry), `DNS` (record resolution with expected values), `TCP` (port connectivity).

Monitors can be organized with `environment` labels and `tags`, and filtered in the monitor list (`?monitor_type=&status=&environment=&tag=`).

### SSL monitors

```bash
curl -X POST http://127.0.0.1:8000/api/v1/monitors/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Client SSL","monitor_type":"SSL","url":"https://clientwebsite.com","interval_seconds":86400,"ssl_expiry_threshold_days":14}'
```

SSL checks read the TLS certificate, store the expiry and issuer on the monitor, mark the monitor `DEGRADED` within the threshold, raise `SSL_EXPIRING` alerts, and fail once the certificate is expired.

### Maintenance windows

Maintenance windows suppress scheduled checks, incident creation, and missed-heartbeat detection for their monitors while active; they are shown on public status pages (active + upcoming).

```bash
curl -X POST http://127.0.0.1:8000/api/v1/maintenance-windows/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","title":"DB upgrade","starts_at":"2026-05-22T01:00:00Z","ends_at":"2026-05-22T03:00:00Z","monitor_ids":["MONITOR_PUBLIC_ID"]}'
```

## Centralized Logging

Applications ship structured logs to WATCHDOG with an API key:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/logs/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: wd_live_..." \
  -d '{"logs":[{"application":"checkout-api","level":"ERROR","message":"payment declined"}]}'
```

- Batches up to 500 entries; levels normalized (`warn`→`WARNING`, `fatal`→`CRITICAL`).
- Secret material (bearer/JWT tokens, `password:` values, card-like numbers, sensitive attribute keys) is redacted at ingestion time and never stored.
- Query with JWT auth: `GET /api/v1/logs/?organization_id=&application=&level=&search=`; aggregates for charts: `GET /api/v1/logs/stats?organization_id=&period=24h`.
- Retention: the scheduler purges logs older than `LOG_RETENTION_DAYS` (default 30); `DELETE /api/v1/logs/retention?organization_id=&retention_days=` purges on demand.

## Infrastructure Monitoring

Install the agent on any Linux host (see [agent/README.md](agent/README.md)):

```bash
pip install psutil
python agent/watchdog_agent.py --api-url http://watchdog:8000/api/v1 \
  --api-key wd_live_... --interval 60 --watch nginx,postgres
```

The agent reports CPU, memory, disk, network utilization, top processes, and watched-service status. Configure per-host thresholds (CPU/memory/disk %, required services) under `/api/v1/infrastructure/thresholds`; the scheduler evaluates them every few minutes and raises deduplicated alerts through your alert channels.

## Distributed Tracing (OpenTelemetry)

WATCHDOG accepts OTLP/JSON trace exports. Point an OpenTelemetry SDK exporter at:

```text
POST /api/v1/traces/ingest   (X-API-Key auth, traces:write scope)
```

The endpoint accepts standard `resourceSpans` OTLP/JSON payloads (and a simple native `{"spans": [...]}` format). Query recent traces, one trace's span waterfall, and the derived service dependency map:

```text
GET /api/v1/traces/?organization_id=&period=24h
GET /api/v1/traces/{trace_id}?organization_id=
GET /api/v1/traces/service-map?organization_id=&period=24h
```

## SLOs and Error Budgets

Define an SLO against any monitor (target % over a rolling window of days); WATCHDOG computes attainment from check results and the remaining error budget:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/slos/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"organization_id":"ORG_PUBLIC_ID","monitor_id":"MONITOR_PUBLIC_ID","name":"API 99.9","target_percentage":99.9,"window_days":30}'
curl http://127.0.0.1:8000/api/v1/slos/SLO_PUBLIC_ID/status -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Anomaly detection runs automatically: response times more than 3σ above the recent baseline raise `ANOMALY` alerts alongside the threshold rules.

## Dashboards

Reusable dashboard templates (`/api/v1/dashboards`) compose widgets — monitor status, uptime, response times, log volume, host health, incidents, service map, SLO status — into shareable layouts. Historical chart data comes from `/api/v1/analytics/response-times`, `/api/v1/analytics/uptime`, and `/api/v1/analytics/service-health`. Correlated incident timelines (updates + alerts + failed checks + related log errors) are available at `/api/v1/analytics/incidents/{id}/timeline`.

## Troubleshooting

### Frontend cannot connect to backend

Check:

- Backend is running at `http://127.0.0.1:8000`.
- Frontend is running at `http://127.0.0.1:5173`.
- `frontend/.env` has `VITE_API_BASE_URL=/api/v1`.
- `frontend/vite.config.ts` proxies `/api` to `http://127.0.0.1:8000`.
- Backend `CORS_ORIGINS` includes the frontend origin.

### Verification email is not sent

Check:

- `EMAIL_ENABLED=true`
- `RESENT_API_KEY` or `RESEND_API_KEY` is set
- `FROM_EMAIL` is verified in Resend
- Restart the backend after changing `.env`

### Monitor URL is blocked as unsafe

WATCHDOG blocks unsafe monitor URLs and hostnames that do not resolve. Use public, resolvable URLs for website/API monitors.

### Database columns are missing

Apply migrations:

```powershell
python -m alembic upgrade head
```
