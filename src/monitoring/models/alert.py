from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring.models.base import Base

if TYPE_CHECKING:
    from monitoring.models.monitor import Monitor


class Alert(Base):
    """Alert model for storing triggered alerts."""

    __tablename__ = "alerts"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign key to monitor
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Alert details
    severity: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'info', 'warning', 'error', 'critical'
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Alert state
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship
    monitor: Mapped[Monitor] = relationship()

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id}, monitor_id={self.monitor_id}, "
            f"severity='{self.severity}')>"
        )
