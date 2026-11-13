"""API integration tests for the observability endpoints (API keys, logs, maintenance windows)."""

from __future__ import annotations

import pytest

from tests.integration.test_api._helpers import (
    create_organization,
    make_client,
    register_and_login,
    release_client,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _release_overrides():
    yield
    release_client()


async def _setup_org(test_db):
    """Create the client (already opened, not closed) plus auth headers and org.

    Returns (client, headers, org). The caller must NOT use `async with` on the
    client again — use it directly and call release_client() when done.
    """
    client = await make_client(test_db)
    auth = await register_and_login(client, test_db)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    org = await create_organization(client, headers)
    return client, headers, org


async def test_api_keys_crud_and_show_once(test_db) -> None:
    client, headers, org = await _setup_org(test_db)
    created = await client.post(
    "/api/v1/api-keys/",
    json={"organization_id": org["public_id"], "name": "agent key"},
    headers=headers,
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["key"].startswith("wd_live_")
    assert payload["key_prefix"] in payload["key"]
    listed = await client.get(
    f"/api/v1/api-keys/?organization_id={org['public_id']}",
    headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["api_keys"][0]["key_prefix"] == payload["key_prefix"]
    revoked = await client.delete(f"/api/v1/api-keys/{payload['id']}", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    after = await client.get(
    f"/api/v1/api-keys/?organization_id={org['public_id']}",
    headers=headers,
    )
    assert after.json()["api_keys"][0]["revoked_at"] is not None
async def test_log_ingestion_requires_api_key(test_db) -> None:
    client, headers, org = await _setup_org(test_db)
    batch = {"logs": [{"application": "app", "level": "INFO", "message": "hello"}]}
# No key at all -> 401
    anonymous = await client.post("/api/v1/logs/ingest", json=batch)
    assert anonymous.status_code == 401
# Bogus key -> 401
    bogus = await client.post(
    "/api/v1/logs/ingest",
    json=batch,
    headers={"X-API-Key": "wd_live_bogus"},
    )
    assert bogus.status_code == 401
# JWT tokens are not API keys -> 401
    jwt_only = await client.post("/api/v1/logs/ingest", json=batch, headers=headers)
    assert jwt_only.status_code == 401
async def test_log_ingest_search_and_redaction(test_db) -> None:
    client, headers, org = await _setup_org(test_db)
    created = await client.post(
    "/api/v1/api-keys/",
    json={"organization_id": org["public_id"], "name": "ingest"},
    headers=headers,
    )
    raw_key = created.json()["key"]
    key_headers = {"X-API-Key": raw_key}
    batch = {
    "logs": [
        {"application": "checkout-api", "level": "ERROR", "message": "declined with password=hunter2secret"},
        {"application": "checkout-api", "level": "warn", "message": "slow"},
        {"application": "web", "level": "INFO", "message": "ok"},
    ],
    }
    ingested = await client.post("/api/v1/logs/ingest", json=batch, headers=key_headers)
    assert ingested.status_code == 202, ingested.text
    assert ingested.json() == {"accepted": 3, "rejected": 0}
# Bad level is rejected but the rest of the batch is accepted
    partial = {
    "logs": [
        {"application": "web", "level": "INFO", "message": "fine"},
        {"application": "web", "level": "NOT_A_LEVEL", "message": "bad"},
    ],
    }
    partial_result = await client.post("/api/v1/logs/ingest", json=partial, headers=key_headers)
    assert partial_result.status_code == 202
    assert partial_result.json() == {"accepted": 1, "rejected": 1}
# Search with JWT: redaction applied, filters work
    errors = await client.get(
    f"/api/v1/logs/?organization_id={org['public_id']}&level=ERROR",
    headers=headers,
    )
    assert errors.status_code == 200
    assert errors.json()["total"] == 1
    message = errors.json()["logs"][0]["message"]
    assert "hunter2secret" not in message
    assert "[REDACTED]" in message
# Application filter
    web_logs = await client.get(
    f"/api/v1/logs/?organization_id={org['public_id']}&application=web",
    headers=headers,
    )
    assert web_logs.json()["total"] == 2
# Stats endpoint
    stats = await client.get(
    f"/api/v1/logs/stats?organization_id={org['public_id']}&period=24h",
    headers=headers,
    )
    assert stats.status_code == 200
    stats_body = stats.json()
    assert stats_body["total"] == 4
    assert stats_body["error_count"] == 1
    assert stats_body["errors_by_application"] == {"checkout-api": 1}
    assert stats_body["volume"]
# Org isolation: another organization sees nothing
    other = await create_organization(client, headers, name="Other Org")
    other_logs = await client.get(
    f"/api/v1/logs/?organization_id={other['public_id']}",
    headers=headers,
    )
    assert other_logs.json()["total"] == 0
async def test_maintenance_window_crud_flow(test_db) -> None:
    client, headers, org = await _setup_org(test_db)
# Create a monitor to attach
    monitor = await client.post(
    "/api/v1/monitors/",
    json={
        "organization_id": org["public_id"],
        "name": "API",
        "url": "https://api.example.com",
        "interval_seconds": 60,
    },
    headers=headers,
    )
    assert monitor.status_code == 201, monitor.text
    monitor_public_id = monitor.json()["public_id"]
    created = await client.post(
    "/api/v1/maintenance-windows/",
    json={
        "organization_id": org["public_id"],
        "title": "DB upgrade",
        "starts_at": "2099-01-01T01:00:00Z",
        "ends_at": "2099-01-01T03:00:00Z",
        "monitor_ids": [monitor_public_id],
    },
    headers=headers,
    )
    assert created.status_code == 201, created.text
    window = created.json()
    assert window["monitor_ids"] == [monitor_public_id]
    listed = await client.get(
    f"/api/v1/maintenance-windows/?organization_id={org['public_id']}",
    headers=headers,
    )
    assert listed.json()["total"] == 1
    patched = await client.patch(
    f"/api/v1/maintenance-windows/{window['id']}",
    json={"title": "DB upgrade v2", "monitor_ids": []},
    headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "DB upgrade v2"
    assert patched.json()["monitor_ids"] == []
    deleted = await client.delete(f"/api/v1/maintenance-windows/{window['id']}", headers=headers)
    assert deleted.status_code == 204
    gone = await client.get(
    f"/api/v1/maintenance-windows/?organization_id={org['public_id']}",
    headers=headers,
    )
    assert gone.json()["total"] == 0
async def test_maintenance_invalid_period_rejected(test_db) -> None:
    client, headers, org = await _setup_org(test_db)
    bad = await client.post(
    "/api/v1/maintenance-windows/",
    json={
        "organization_id": org["public_id"],
        "title": "Backwards",
        "starts_at": "2099-01-01T03:00:00Z",
        "ends_at": "2099-01-01T01:00:00Z",
    },
    headers=headers,
    )
    assert bad.status_code == 422
async def test_monitor_tag_and_environment_filters(test_db) -> None:
    client, headers, org = await _setup_org(test_db)
    await client.post(
    "/api/v1/monitors/",
    json={
        "organization_id": org["public_id"],
        "name": "Tagged",
        "url": "https://a.example.com",
        "interval_seconds": 60,
        "environment": "production",
        "tags": ["critical", "payments"],
    },
    headers=headers,
    )
    await client.post(
    "/api/v1/monitors/",
    json={
        "organization_id": org["public_id"],
        "name": "Untagged",
        "url": "https://b.example.com",
        "interval_seconds": 60,
        "environment": "staging",
    },
    headers=headers,
    )
    tagged = await client.get(
    f"/api/v1/monitors/?organization_id={org['public_id']}&tag=critical",
    headers=headers,
    )
    assert tagged.json()["total"] == 1
    assert tagged.json()["monitors"][0]["name"] == "Tagged"
    prod = await client.get(
    f"/api/v1/monitors/?organization_id={org['public_id']}&environment=production",
    headers=headers,
    )
    assert prod.json()["total"] == 1
    by_type = await client.get(
    f"/api/v1/monitors/?organization_id={org['public_id']}&monitor_type=WEBSITE",
    headers=headers,
    )
    assert by_type.json()["total"] == 2
async def test_infrastructure_threshold_endpoints(test_db) -> None:
    client, headers, org = await _setup_org(test_db)
    created = await client.post(
    "/api/v1/infrastructure/thresholds",
    json={
        "organization_id": org["public_id"],
        "host": "web-01",
        "cpu_percent": 80,
        "process_names": ["nginx"],
    },
    headers=headers,
    )
    assert created.status_code == 201, created.text
    threshold = created.json()
    assert threshold["host"] == "web-01"
    patched = await client.patch(
    f"/api/v1/infrastructure/thresholds/{threshold['id']}",
    json={"cpu_percent": 85, "enabled": False},
    headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["cpu_percent"] == 85
    listed = await client.get(
    f"/api/v1/infrastructure/thresholds?organization_id={org['public_id']}",
    headers=headers,
    )
    assert listed.json()["total"] == 1
    removed = await client.delete(f"/api/v1/infrastructure/thresholds/{threshold['id']}", headers=headers)
    assert removed.status_code == 204
