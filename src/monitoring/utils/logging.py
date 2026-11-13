from __future__ import annotations

import logging
import sys
from typing import cast

import structlog

from monitoring.config import get_settings
from monitoring.utils.redaction import redact_text


def _redact_processor(
    logger: object,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Redact secret-looking material from log messages and string fields."""
    event = event_dict.get("event")
    if isinstance(event, str):
        event_dict["event"] = redact_text(event)
    for key, value in event_dict.items():
        if key != "event" and isinstance(value, str):
            event_dict[key] = redact_text(value)
    return event_dict


def setup_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            _redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Structured logger
    """
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
