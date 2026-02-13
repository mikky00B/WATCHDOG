from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AlertPayload:
    """Standardized alert payload for delivery."""
    monitor_name: str
    severity: str
    title: str
    message: str
    timestamp: str
    monitor_url: str | None = None
    alert_id: int = 0


class AlertChannel(ABC):
    """Abstract base class for alert delivery channels."""

    @abstractmethod
    async def send(self, payload: AlertPayload) -> bool:
        """
        Send alert through this channel.

        Args:
            payload: Alert data to send

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate channel configuration.

        Returns:
            True if configuration is valid, False otherwise
        """
        pass
