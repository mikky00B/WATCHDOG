from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring.models.base import Base

if TYPE_CHECKING:
    from monitoring.models.monitor import Monitor
    from monitoring.models.organization import Organization


class MaintenanceWindow(Base):
    """Scheduled maintenance window suppressing monitor checks and alerting."""

    __tablename__ = "maintenance_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    public_id: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    notify_subscribers: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
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

    organization: Mapped[Organization] = relationship()
    monitors: Mapped[list[MaintenanceWindowMonitor]] = relationship(
        back_populates="maintenance_window",
        cascade="all, delete-orphan",
    )

    def is_active(self, now: datetime) -> bool:
        return self.starts_at <= now < self.ends_at

    def __repr__(self) -> str:
        return f"<MaintenanceWindow(id={self.id}, title='{self.title}')>"


class MaintenanceWindowMonitor(Base):
    """Association between a maintenance window and the monitors it covers.

    A window with no associated monitors covers the whole organization.
    """

    __tablename__ = "maintenance_window_monitors"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_window_id",
            "monitor_id",
            name="uq_maintenance_window_monitor",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    maintenance_window_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_windows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    maintenance_window: Mapped[MaintenanceWindow] = relationship(back_populates="monitors")
    monitor: Mapped[Monitor] = relationship()
