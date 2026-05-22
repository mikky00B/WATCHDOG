from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring.models.base import Base

if TYPE_CHECKING:
    from monitoring.models.check_result import CheckResult
    from monitoring.models.client import Client


class Monitor(Base):
    """Monitor model for tracking endpoints to monitor."""

    __tablename__ = "monitors"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Public UUID for API exposure
    public_id: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    # Monitor details
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    monitor_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="http",
    )  # 'http', 'heartbeat', 'dependency'
    heartbeat_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    # Check configuration
    http_method: Mapped[str] = mapped_column(String(20), default="GET", nullable=False)
    expected_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    request_headers: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    response_time_threshold_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tracking
    status: Mapped[str] = mapped_column(String(50), default="UNKNOWN", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Timestamps
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

    # Relationships
    check_results: Mapped[list[CheckResult]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
    )
    client: Mapped[Client | None] = relationship(back_populates="monitors")

    def __repr__(self) -> str:
        return f"<Monitor(id={self.id}, name='{self.name}', url='{self.url}')>"
