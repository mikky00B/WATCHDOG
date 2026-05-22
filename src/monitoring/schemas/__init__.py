from __future__ import annotations

from monitoring.schemas.alert import (
    AlertCreate,
    AlertList,
    AlertResponse,
    AlertSeverity,
    AlertUpdate,
)
from monitoring.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from monitoring.schemas.check import (
    CheckResultCreate,
    CheckResultList,
    CheckResultResponse,
)
from monitoring.schemas.client import ClientCreate, ClientList, ClientResponse, ClientUpdate
from monitoring.schemas.heartbeat import (
    HeartbeatCreate,
    HeartbeatList,
    HeartbeatPing,
    HeartbeatResponse,
    HeartbeatUpdate,
)
from monitoring.schemas.incident import (
    IncidentCreate,
    IncidentList,
    IncidentResponse,
    IncidentSeverity,
    IncidentStatus,
    IncidentUpdateCreate,
    IncidentUpdateResponse,
)
from monitoring.schemas.monitor import (
    MonitorCreate,
    MonitorList,
    MonitorResponse,
    MonitorUpdate,
)
from monitoring.schemas.notification import (
    AlertEventResponse,
    NotificationChannelCreate,
    NotificationChannelList,
    NotificationChannelResponse,
    NotificationChannelType,
    NotificationChannelUpdate,
)
from monitoring.schemas.organization import (
    OrganizationCreate,
    OrganizationList,
    OrganizationResponse,
)
from monitoring.schemas.report import (
    MonthlyReportResponse,
    ReportIncidentSummary,
    ReportMonitorSummary,
)
from monitoring.schemas.status_page import (
    PublicStatusPageResponse,
    PublicStatusService,
    StatusPageCreate,
    StatusPageList,
    StatusPageResponse,
    StatusPageServiceCreate,
    StatusPageServiceResponse,
    StatusPageUpdate,
)

__all__ = [
    # Monitor
    "MonitorCreate",
    "MonitorUpdate",
    "MonitorResponse",
    "MonitorList",
    # Check
    "CheckResultCreate",
    "CheckResultResponse",
    "CheckResultList",
    # Clients
    "ClientCreate",
    "ClientUpdate",
    "ClientResponse",
    "ClientList",
    # Alert
    "AlertCreate",
    "AlertUpdate",
    "AlertResponse",
    "AlertList",
    "AlertSeverity",
    # Heartbeat
    "HeartbeatCreate",
    "HeartbeatUpdate",
    "HeartbeatResponse",
    "HeartbeatPing",
    "HeartbeatList",
    # Incidents
    "IncidentCreate",
    "IncidentResponse",
    "IncidentList",
    "IncidentStatus",
    "IncidentSeverity",
    "IncidentUpdateCreate",
    "IncidentUpdateResponse",
    # Auth
    "RegisterRequest",
    "RegisterResponse",
    "LoginRequest",
    "VerifyEmailRequest",
    "ResendVerificationRequest",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
    "RefreshTokenRequest",
    "LogoutRequest",
    "TokenResponse",
    "UserResponse",
    # Organizations
    "OrganizationCreate",
    "OrganizationResponse",
    "OrganizationList",
    # Reports
    "ReportMonitorSummary",
    "ReportIncidentSummary",
    "MonthlyReportResponse",
    # Notifications
    "NotificationChannelCreate",
    "NotificationChannelUpdate",
    "NotificationChannelResponse",
    "NotificationChannelList",
    "NotificationChannelType",
    "AlertEventResponse",
    # Status pages
    "StatusPageCreate",
    "StatusPageUpdate",
    "StatusPageResponse",
    "StatusPageList",
    "StatusPageServiceCreate",
    "StatusPageServiceResponse",
    "PublicStatusService",
    "PublicStatusPageResponse",
]
