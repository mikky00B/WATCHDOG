# WATCHDOG Monitoring Platform

WATCHDOG is a FastAPI and React monitoring platform for agencies and teams that need uptime checks, heartbeat checks, incidents, client grouping, alert channels, status pages, and monthly reliability reports.


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
SMTP_HOST=smtp.titan.email
SMTP_PORT=465
SMTP_USER=michael@example.com
SMTP_PASSWORD="your-mailbox-or-app-password"
FROM_EMAIL=michael@example.com

TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_WEBHOOK_SECRET=your-random-webhook-secret
TELEGRAM_WEBHOOK_URL=https://your-domain.com/api/v1/integrations/telegram/webhook
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
```

SMTP notes:

- Port `465` uses implicit SSL automatically.
- Port `587` uses STARTTLS.
- Titan Mail requires third-party email access to be enabled for the mailbox.
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
6. Create monitors.
7. Add alert channels for the organization.
8. Create a status page and add monitor services.
9. Use Reports to generate monthly reliability summaries.

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
  -d '{"organization_id":"ORG_PUBLIC_ID","name":"Website","url":"https://example.com","monitor_type":"WEBSITE","interval_seconds":60}'
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

Reports are generated on demand and are not persisted yet. PDF export and scheduled report emails are not implemented.

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
│   ├── alerting/            # Email, Telegram, Slack, webhook, transactional email
│   ├── api/v1/              # REST routes
│   ├── core/                # Password hashing and token helpers
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic
│   ├── utils/               # Logging and URL safety
│   └── workers/             # Scheduler and notification worker
├── alembic/                 # Database migrations
├── tests/                   # Unit and integration tests
├── scripts/                 # Utility scripts
├── requirements.txt
├── pyproject.toml
└── README.md
```

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
- SMTP credentials are correct
- Titan third-party email access is enabled if using Titan Mail
- Port `465` uses SSL/TLS; port `587` uses STARTTLS
- Restart the backend after changing `.env`

### Monitor URL is blocked as unsafe

WATCHDOG blocks unsafe monitor URLs and hostnames that do not resolve. Use public, resolvable URLs for website/API monitors.

### Database columns are missing

Apply migrations:

```powershell
python -m alembic upgrade head
```
