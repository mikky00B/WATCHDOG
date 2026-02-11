from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring.models.base import Base

if TYPE_CHECKING:
    from monitoring.models.check_result import CheckResult


class Monitor(Base):
    """Monitor model for tracking endpoints to monitor."""

    __tablename__ = "monitors"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Public UUID for API exposure
    public_id: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    # Monitor details
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    monitor_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="http",
    )  # 'http', 'heartbeat', 'dependency'

    # Check configuration
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tracking
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    def __repr__(self) -> str:
        return f"<Monitor(id={self.id}, name='{self.name}', url='{self.url}')>"
