#!/usr/bin/env python3
"""Run background workers for monitoring."""
from __future__ import annotations

import asyncio

from monitoring.alerting.email import EmailAlertChannel
from monitoring.config import get_settings
from monitoring.services.checker_service import CheckerService
from monitoring.services.rule_engine import RuleEngine
from monitoring.utils.logging import get_logger, setup_logging
from monitoring.workers.alert_worker import AlertWorker
from monitoring.workers.scheduler import MonitorScheduler

setup_logging()
logger = get_logger(__name__)

settings = get_settings()


async def main() -> None:
    """Run the monitoring scheduler and alert worker."""
    logger.info("starting_workers")

    # Create services with rate limiting
    checker_service = CheckerService(
        max_concurrent=settings.max_concurrent_checks,
        requests_per_minute=settings.requests_per_minute_per_site,
        max_retries=settings.max_check_retries,
    )

    # Create rule engine
    rule_engine = RuleEngine()

    # Create scheduler
    scheduler = MonitorScheduler(
        checker_service=checker_service,
        rule_engine=rule_engine,
    )

    # Create alert channels
    channels = []

    # Add email channel if configured
    if settings.email_enabled:
        try:
            email_channel = EmailAlertChannel(
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=settings.smtp_password,
                from_email=settings.from_email,
                to_emails=settings.alert_emails,
                use_html=True,
            )

            # Test connection before starting
            logger.info("testing_email_connection")
            if await email_channel.test_connection():
                channels.append(email_channel)
                logger.info(
                    "email_channel_enabled",
                    smtp_host=settings.smtp_host,
                    to_emails=settings.alert_emails,
                )
            else:
                logger.error("email_connection_test_failed")
        except Exception as exc:
            logger.error(
                "email_channel_setup_failed",
                error=str(exc),
                exc_info=True,
            )
    else:
        logger.warning("email_alerts_disabled")

    # Create alert worker
    if channels:
        alert_worker = AlertWorker(
            channels=channels,
            batch_size=100,
            check_interval_seconds=5,
            max_retries=3,
            retry_delay_seconds=60,
        )
        logger.info("alert_worker_created", channel_count=len(channels))
    else:
        alert_worker = None
        logger.warning("no_alert_channels_configured")

    try:
        # Run both scheduler and alert worker concurrently
        tasks = [scheduler.start()]

        if alert_worker:
            tasks.append(alert_worker.start())

        await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        logger.info("shutdown_requested")
        await scheduler.stop()
        if alert_worker:
            await alert_worker.stop()
    except Exception as exc:
        logger.error("worker_error", error=str(exc), exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
