from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.organization import Organization
from monitoring.models.user import User
from monitoring.models.monitor import Monitor
from monitoring.schemas.auth import RegisterRequest
from monitoring.schemas.status_page import StatusPageCreate, StatusPageServiceCreate, StatusPageUpdate
from monitoring.services.auth_service import AuthService
from monitoring.services.status_page_service import StatusPageService


@pytest.mark.unit
async def test_auth_service_core_branches(test_db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    service = AuthService(test_db)
    monkeypatch.setattr(service, "_send_verification_email", pytest.MonkeyPatch().setattr if False else None)
