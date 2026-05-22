from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring.models.base import Base


class StatusPage(Base):
    """Public status page owned by an organization."""

    __tablename__ = "status_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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

    services: Mapped[list[StatusPageService]] = relationship(
        back_populates="status_page",
        cascade="all, delete-orphan",
    )


class StatusPageService(Base):
    """Monitor exposed as a service on a status page."""

    __tablename__ = "status_page_services"
    __table_args__ = (
        UniqueConstraint("status_page_id", "monitor_id", name="uq_status_page_monitor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, unique=True, index=True)
    status_page_id: Mapped[int] = mapped_column(
        ForeignKey("status_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    status_page: Mapped[StatusPage] = relationship(back_populates="services")
