from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from monitoring.models.base import Base


class Heartbeat(Base):
    """Heartbeat model for tracking service heartbeats."""

    __tablename__ = "heartbeats"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Public UUID for heartbeat endpoint
    public_id: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    # Heartbeat details
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Expected interval
    expected_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    # Last heartbeat
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
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

    def __repr__(self) -> str:
        return f"<Heartbeat(id={self.id}, name='{self.name}')>"
