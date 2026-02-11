from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring.models.base import Base

if TYPE_CHECKING:
    from monitoring.models.monitor import Monitor


class CheckResult(Base):
    """Check result model for storing monitor check outcomes."""

    __tablename__ = "check_results"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign key to monitor
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Check results
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Timestamp
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationship
    monitor: Mapped[Monitor] = relationship(back_populates="check_results")

    def __repr__(self) -> str:
        return (
            f"<CheckResult(id={self.id}, monitor_id={self.monitor_id}, "
            f"success={self.success})>"
        )
