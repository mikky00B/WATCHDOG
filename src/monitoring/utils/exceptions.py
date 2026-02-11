from __future__ import annotations


class MonitoringException(Exception):
    """Base exception for monitoring platform."""

    pass


class MonitorNotFoundError(MonitoringException):
    """Raised when a monitor cannot be found."""

    def __init__(self, monitor_id: int | str):
        self.monitor_id = monitor_id
        super().__init__(f"Monitor {monitor_id} not found")


class AlertNotFoundError(MonitoringException):
    """Raised when an alert cannot be found."""

    def __init__(self, alert_id: int):
        self.alert_id = alert_id
        super().__init__(f"Alert {alert_id} not found")


class HeartbeatNotFoundError(MonitoringException):
    """Raised when a heartbeat cannot be found."""

    def __init__(self, heartbeat_id: str):
        self.heartbeat_id = heartbeat_id
        super().__init__(f"Heartbeat {heartbeat_id} not found")


class CheckError(MonitoringException):
    """Raised when a health check fails."""

    def __init__(self, monitor_id: int, reason: str):
        self.monitor_id = monitor_id
        self.reason = reason
        super().__init__(f"Check failed for monitor {monitor_id}: {reason}")


class AlertDeliveryError(MonitoringException):
    """Raised when alert delivery fails."""

    def __init__(self, alert_id: int, channel: str, reason: str):
        self.alert_id = alert_id
        self.channel = channel
        self.reason = reason
        super().__init__(
            f"Failed to deliver alert {alert_id} via {channel}: {reason}"
        )
