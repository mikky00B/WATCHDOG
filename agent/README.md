# WATCHDOG Infrastructure Agent

A lightweight Linux agent that reports CPU, memory, disk, network utilization,
top processes, and watched-service status to WATCHDOG.

## Install

```bash
pip install psutil
```

That is the only dependency — the agent itself is a single stdlib script.

## Create an API key

In the WATCHDOG dashboard, create an API key (Dashboard → API Keys) with at
least the `metrics:write` scope. Keys look like `wd_live_...`.

## Run

```bash
python agent/watchdog_agent.py \
  --api-url http://your-watchdog-host:8000/api/v1 \
  --api-key wd_live_XXXXXXXX \
  --interval 60 \
  --watch nginx,postgres \
  --host web-01 \
  --environment production
```

- `--interval` — sampling interval in seconds (minimum 10, default 60)
- `--watch` — comma-separated process names; a missing process raises an
  infrastructure alert when a threshold exists for this host
- `--host` — label shown in the dashboard (defaults to the machine hostname)

Environment-variable equivalents: `WATCHDOG_API_URL`, `WATCHDOG_API_KEY`,
`WATCHDOG_INTERVAL`, `WATCHDOG_HOST`, `WATCHDOG_WATCH`, `WATCHDOG_ENVIRONMENT`.

## Run as a systemd service

`/etc/systemd/system/watchdog-agent.service`:

```ini
[Unit]
Description=WATCHDOG Infrastructure Agent
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 /opt/watchdog/agent/watchdog_agent.py \
    --api-url https://watchdog.example.com/api/v1 \
    --api-key wd_live_XXXXXXXX \
    --interval 60 \
    --watch nginx,postgres
Restart=always
RestartSec=10
User=nobody

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now watchdog-agent
```

## Alerts

Configure per-host thresholds in the dashboard (Infrastructure → Thresholds):
CPU %, memory %, disk %, and required services. The backend evaluates the
latest metrics every few minutes and raises deduplicated alerts through your
organization's alert channels.
