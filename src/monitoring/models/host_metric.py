from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from monitoring.models.base import Base


class HostMetric(Base):
    """Infrastructure metrics sample for one host, reported by the WATCHDOG agent."""

    __tablename__ = "host_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    environment: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_used_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_used_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_in_kb_per_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_out_kb_per_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Top processes: [{"pid": 123, "name": "python", "cpu": 4.2, "memory": 1.8}, ...]
    processes: Mapped[list[object] | None] = mapped_column(JSON, nullable=True)
    # Watched service/process status: {"nginx": true, "postgres": false}
    service_checks: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HostMetric(id={self.id}, host='{self.host}', cpu={self.cpu_percent})>"


class HostThreshold(Base):
    """Alert thresholds for one monitored host."""

    __tablename__ = "host_thresholds"
    __table_args__ = (
        UniqueConstraint("organization_id", "host", name="uq_host_threshold_org_host"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Service names that must be running; a missing process raises an alert.
    process_names: Mapped[list[object] | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HostThreshold(id={self.id}, host='{self.host}')>"
