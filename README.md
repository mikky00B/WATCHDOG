# WATCHDOG — A Production-Grade Monitoring Platform

> A production-ready uptime monitoring system built with FastAPI. Monitor HTTP 
endpoints and heartbeats, receive intelligent alerts via email, and track your 
infrastructure's health in real-time.

**Key Features:** Rate-limited health checks • Smart alert deduplication • 
Customizable rules • Beautiful email notifications • RESTful API. 

---

## 🚀 Getting Started (Manual Setup)

This guide provides instructions for setting up the project.

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 12+ (and its command-line tools like `createdb`)
- A Python package manager (`pip` is used in this guide)

### 2. Clone the Repository

```bash
git clone <https://github.com/mikky00B/WATCHDOG>
cd monitoring-platform
```

### 3. Set Up a Python Environment

It is highly recommended to use a virtual environment.

```bash
# Create a virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 4. Install Dependencies

This project uses a **`src` layout**. For imports to work correctly, the `monitoring` package must be installed in "editable" mode.

```bash
# Install required libraries AND the project package
pip install -r requirements.txt
pip install -e .
```
> **Note:** The `pip install -e .` command inspects `setup.py` and makes the `src/monitoring` directory available as an importable package (`import monitoring.*`) throughout your environment.

### 5. Set Up the Database

You need a running PostgreSQL instance.

```bash
# 1. Ensure your PostgreSQL service is running.

# 2. Create the database for this project
createdb monitoring_db

# (If your local postgres user requires a password, you'll need to configure it accordingly)
```

### 6. Configure Environment Variables

Copy the example `.env` file and edit it to match your local database configuration.

```bash
# 1. Create your .env file
cp .env.example .env

# 2. Open .env in an editor and set your DATABASE_URL
# Example:
DATABASE_URL=postgresql+asyncpg://YOUR_POSTGRES_USER:YOUR_POSTGRES_PASSWORD@localhost:5432/monitoring_db
```

### 7. Run Database Migrations

Apply the database schema to your newly created database.

```bash
alembic upgrade head
```

### 8. Run the Application

The application consists of two separate processes that must be run in two separate terminals.

**Terminal 1: Start the API Server**
```bash
uvicorn monitoring.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2: Start the Background Worker**
```bash
python scripts/run_worker.py
```

### 9. You're Done!

Once both processes are running, you can access:
- **Dashboard**: http://localhost:8000/dashboard
- **API Docs**: http://localhost:8000/docs

---

## Configuration (`.env`)

```env
# Required
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/monitoring_db

# Optional
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
DEFAULT_CHECK_INTERVAL=60
DEFAULT_TIMEOUT=5.0
MAX_CONCURRENT_CHECKS=100

# Email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=alerts@example.com

# Slack alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

---

## Features

- **HTTP endpoint monitoring** — configurable intervals and timeouts
- **Heartbeat tracking** — detect missed service pings
- **Alert rule engine** — consecutive failures, latency thresholds
- **Multi-channel alerts** — Webhook, Email, Slack
- **Background scheduler** — async health checks
- **Dashboard UI** — live at `/dashboard`
- **REST API** — full CRUD with OpenAPI docs at `/docs`

---

## API Examples

```bash
# Create a monitor
curl -X POST http://localhost:8000/api/v1/monitors \
  -H "Content-Type: application/json" \
  -d '{"name":"My API","url":"https://api.example.com/health","interval_seconds":60}'

# List monitors
curl http://localhost:8000/api/v1/monitors

# Get stats (used by dashboard)
curl http://localhost:8000/api/v1/stats

# List active alerts
curl http://localhost:8000/api/v1/alerts?unresolved_only=true

# Ping a heartbeat
curl -X POST http://localhost:8000/api/v1/heartbeats/{id}/ping
```

---

## Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "Add X field"

# Roll back one step
alembic downgrade -1
```

---

## Testing

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=src/monitoring --cov-report=html

# Unit tests only
pytest -m unit
```

---

## Project Structure

```
monitoring-platform/
├── src/monitoring/          # ← Python package (src layout)
│   ├── main.py             # FastAPI app + lifespan
│   ├── config.py           # pydantic-settings
│   ├── database.py         # SQLAlchemy async engine
│   ├── dependencies.py     # FastAPI DI helpers
│   ├── dashboard/          # Static HTML dashboard (served at /dashboard)
│   ├── models/             # SQLAlchemy ORM models (v2.0 Mapped syntax)
│   ├── schemas/            # Pydantic v2 schemas
│   ├── api/v1/             # REST endpoints
│   ├── services/           # Business logic
│   ├── workers/            # Async scheduler + alert worker
│   ├── alerting/           # Webhook / Email / Slack channels
│   └── utils/              # Logging, exceptions
├── alembic/                # Database migrations
├── tests/                  # pytest suite
├── scripts/                # seed_db.py, run_worker.py
├── setup.py                # Package registration (enables pip install -e .)
├── requirements.txt        # Pinned dependencies
└── pyproject.toml          # Poetry config (optional)
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'monitoring'`

The package is not installed. Fix with:

```bash
# Make sure your virtual environment is active, then run:
pip install -e .
```

### `asyncpg` connection error

```bash
# 1. Check PostgreSQL is running
pg_isready -h localhost

# 2. Verify your DATABASE_URL in the .env file
# Format: postgresql+asyncpg://USER:PASS@HOST:PORT/DBNAME
```

### Alembic `ModuleNotFoundError`

```bash
# Run from the project root (not from inside the alembic/ directory)
# and ensure your virtual environment is active.
alembic upgrade head
```

---

