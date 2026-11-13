from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.trace_span import TraceSpan
from monitoring.schemas.trace import TraceSpanIngest

logger = structlog.get_logger(__name__)

# OTLP numeric status codes -> textual
OTLP_STATUS_CODES = {0: "UNSET", 1: "OK", 2: "ERROR"}
OTLP_SPAN_KINDS = {
    0: "UNSPECIFIED",
    1: "INTERNAL",
    2: "SERVER",
    3: "CLIENT",
    4: "PRODUCER",
    5: "CONSUMER",
}


def _otlp_attr_value(value: object) -> object:
    """Extract a Python value from an OTLP JSON typed attribute value."""
    if isinstance(value, dict):
        for key in ("stringValue", "intValue", "doubleValue", "boolValue", "bytesValue"):
            if key in value:
                return value[key]
        if "arrayValue" in value:
            items = value["arrayValue"].get("values", []) or []
            return [_otlp_attr_value(item) for item in items]
        if "kvlistValue" in value:
            kv = value["kvlistValue"].get("values", []) or []
            return {item.get("key"): _otlp_attr_value(item.get("value")) for item in kv}
    return value


def _attrs_to_dict(attributes: list[dict] | None) -> dict[str, object] | None:
    if not attributes:
        return None
    return {
        item.get("key", ""): _otlp_attr_value(item.get("value"))
        for item in attributes
        if item.get("key")
    }


def _nano_to_datetime(nano: int | float | str | None) -> datetime | None:
    if nano in (None, "", 0):
        return None
    try:
        seconds = int(nano) / 1_000_000_000
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


class TraceService:
    """Ingestion and querying of distributed trace spans (OTLP/JSON or native)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_spans(
        self,
        organization_id: int,
        spans: list[TraceSpanIngest],
        application: str | None = None,
        environment: str | None = None,
    ) -> int:
        accepted = 0
        for span in spans:
            start_time = span.start_time
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=UTC)
            end_time = span.end_time
            if end_time is not None and end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=UTC)
            duration_ms = span.duration_ms
            if duration_ms is None and end_time is not None:
                duration_ms = (end_time - start_time).total_seconds() * 1000
            self.db.add(
                TraceSpan(
                    organization_id=organization_id,
                    application=application,
                    environment=environment,
                    trace_id=span.trace_id,
                    span_id=span.span_id,
                    parent_span_id=span.parent_span_id,
                    service=span.service[:255],
                    operation=span.operation[:255],
                    kind=span.kind,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    status=(span.status or "UNSET").upper(),
                    status_message=span.status_message,
                    attributes=span.attributes,
                ),
            )
            accepted += 1
        if accepted:
            await self.db.flush()
        return accepted

    async def ingest_otlp_json(
        self,
        organization_id: int,
        payload: dict,
    ) -> int:
        """Parse an OTLP/JSON ExportTraceServiceRequest and store its spans."""
        accepted = 0
        for resource_spans in payload.get("resourceSpans", []) or []:
            resource = resource_spans.get("resource", {}) or {}
            resource_attrs = _attrs_to_dict(resource.get("attributes"))
            service_name = "unknown-service"
            environment = resource_attrs.get("deployment.environment") if resource_attrs else None
            if isinstance(resource_attrs, dict):
                service_name = str(
                    resource_attrs.get("service.name", "unknown-service"),
                )
                environment = resource_attrs.get("deployment.environment")

            for scope_spans in resource_spans.get("scopeSpans", []) or []:
                for span in scope_spans.get("spans", []) or []:
                    trace_id = span.get("traceId")
                    span_id = span.get("spanId")
                    if not trace_id or not span_id:
                        continue
                    start_time = _nano_to_datetime(span.get("startTimeUnixNano"))
                    end_time = _nano_to_datetime(span.get("endTimeUnixNano"))
                    if start_time is None:
                        continue
                    status = span.get("status") or {}
                    status_code = status.get("code")
                    kind_code = span.get("kind")

                    duration_ms = None
                    if end_time is not None:
                        duration_ms = (end_time - start_time).total_seconds() * 1000

                    self.db.add(
                        TraceSpan(
                            organization_id=organization_id,
                            application=None,
                            environment=str(environment) if environment else None,
                            trace_id=str(trace_id),
                            span_id=str(span_id),
                            parent_span_id=(
                                str(span["parentSpanId"]) if span.get("parentSpanId") else None
                            ),
                            service=service_name[:255],
                            operation=str(span.get("name", "unknown"))[:255],
                            kind=OTLP_SPAN_KINDS.get(kind_code, str(kind_code) if kind_code else None),
                            start_time=start_time,
                            end_time=end_time,
                            duration_ms=duration_ms,
                            status=OTLP_STATUS_CODES.get(status_code, "UNSET"),
                            status_message=status.get("message"),
                            attributes=_attrs_to_dict(span.get("attributes")),
                        ),
                    )
                    accepted += 1
        if accepted:
            await self.db.flush()
        return accepted

    async def get_trace(self, organization_id: int, trace_id: str) -> list[TraceSpan]:
        result = await self.db.execute(
            select(TraceSpan)
            .where(
                TraceSpan.organization_id == organization_id,
                TraceSpan.trace_id == trace_id,
            )
            .order_by(TraceSpan.start_time.asc()),
        )
        return list(result.scalars().all())

    async def list_traces(
        self,
        organization_id: int,
        service: str | None = None,
        hours: float = 24.0,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        """Recent traces summarized per trace_id (newest first)."""
        window_start = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            select(TraceSpan)
            .where(
                TraceSpan.organization_id == organization_id,
                TraceSpan.start_time >= window_start,
            )
            .order_by(TraceSpan.start_time.desc())
            .limit(2000)
        )
        if service:
            stmt = stmt.where(TraceSpan.service == service)
        spans = list((await self.db.execute(stmt)).scalars().all())

        grouped: dict[str, list[TraceSpan]] = {}
        for span in spans:
            grouped.setdefault(span.trace_id, []).append(span)

        summaries: list[dict[str, object]] = []
        for trace_id, trace_spans in grouped.items():
            root = next((s for s in trace_spans if not s.parent_span_id), trace_spans[0])
            services = {s.service for s in trace_spans}
            if service and service not in services:
                continue
            summaries.append(
                {
                    "trace_id": trace_id,
                    "root_service": root.service,
                    "root_operation": root.operation,
                    "span_count": len(trace_spans),
                    "service_count": len(services),
                    "error_count": sum(1 for s in trace_spans if s.status == "ERROR"),
                    "started_at": min(s.start_time for s in trace_spans),
                    "duration_ms": max(
                        (s.duration_ms or 0.0) for s in trace_spans
                    ) or None,
                },
            )
        summaries.sort(key=lambda item: item["started_at"], reverse=True)
        return summaries[:limit]

    async def service_map(
        self,
        organization_id: int,
        hours: float = 24.0,
    ) -> dict[str, object]:
        """Service dependency edges derived from parent/child span relationships."""
        window_start = datetime.now(UTC) - timedelta(hours=hours)
        spans = list(
            (
                await self.db.execute(
                    select(TraceSpan)
                    .where(
                        TraceSpan.organization_id == organization_id,
                        TraceSpan.start_time >= window_start,
                    )
                    .limit(5000),
                )
            ).scalars().all(),
        )

        span_service = {span.span_id: span.service for span in spans}
        edges: dict[tuple[str, str], dict[str, object]] = {}
        services: set[str] = set()
        for span in spans:
            services.add(span.service)
            if not span.parent_span_id:
                continue
            parent_service = span_service.get(span.parent_span_id)
            if parent_service is None or parent_service == span.service:
                continue
            key = (parent_service, span.service)
            edge = edges.setdefault(
                key,
                {"call_count": 0, "duration_sum": 0.0, "error_count": 0},
            )
            edge["call_count"] += 1
            if span.duration_ms is not None:
                edge["duration_sum"] += float(span.duration_ms)
            if span.status == "ERROR":
                edge["error_count"] += 1

        edge_payload = []
        for (source, target), data in edges.items():
            edge_payload.append(
                {
                    "source": source,
                    "target": target,
                    "call_count": data["call_count"],
                    "avg_duration_ms": round(
                        data["duration_sum"] / data["call_count"],
                        1,
                    )
                    if data["call_count"]
                    else None,
                    "error_count": data["error_count"],
                },
            )
        edge_payload.sort(key=lambda e: e["call_count"], reverse=True)
        return {"edges": edge_payload, "services": sorted(services)}

    async def delete_older_than(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.db.execute(delete(TraceSpan).where(TraceSpan.start_time < cutoff))
        await self.db.commit()
        return result.rowcount or 0
