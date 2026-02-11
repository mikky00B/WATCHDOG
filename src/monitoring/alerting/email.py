from __future__ import annotations

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from monitoring.alerting.base import AlertChannel, AlertPayload

logger = structlog.get_logger(__name__)


class EmailAlertChannel(AlertChannel):
    """Send alerts via email with HTML formatting."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str,
        to_emails: list[str],
        use_tls: bool = True,
        use_html: bool = True,
        timeout: int = 30,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls
        self.use_html = use_html
        self.timeout = timeout

    def validate_config(self) -> bool:
        """Validate email configuration."""
        if not all(
            [
                self.smtp_host,
                self.smtp_port,
                self.smtp_user,
                self.smtp_password,
                self.from_email,
                self.to_emails,
            ]
        ):
            logger.error("email_missing_required_config")
            return False

        if not isinstance(self.to_emails, list) or len(self.to_emails) == 0:
            logger.error("email_invalid_recipients")
            return False

        return True

    def _get_severity_color(self, severity: str) -> str:
        """Get color code for severity level."""
        colors = {
            "critical": "#dc3545",  # Red
            "error": "#fd7e14",  # Orange
            "warning": "#ffc107",  # Yellow
            "info": "#17a2b8",  # Blue
        }
        return colors.get(severity.lower(), "#6c757d")  # Default gray

    def _create_html_body(self, payload: AlertPayload) -> str:
        """Create HTML email body."""
        severity_color = self._get_severity_color(payload.severity)

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .container {{
            background-color: #ffffff;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            overflow: hidden;
        }}
        .header {{
            background-color: {severity_color};
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .content {{
            padding: 30px;
        }}
        .info-row {{
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e9ecef;
        }}
        .info-row:last-child {{
            border-bottom: none;
        }}
        .label {{
            font-weight: 600;
            color: #6c757d;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .value {{
            font-size: 16px;
            margin-top: 5px;
        }}
        .severity-badge {{
            display: inline-block;
            padding: 4px 12px;
            background-color: {severity_color};
            color: white;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .message-box {{
            background-color: #f8f9fa;
            border-left: 4px solid {severity_color};
            padding: 15px;
            margin-top: 20px;
            border-radius: 4px;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 15px 30px;
            font-size: 12px;
            color: #6c757d;
            text-align: center;
        }}
        .button {{
            display: inline-block;
            padding: 10px 20px;
            background-color: {severity_color};
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin-top: 15px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Monitor Alert</h1>
        </div>
        <div class="content">
            <div class="info-row">
                <div class="label">Monitor</div>
                <div class="value">{payload.monitor_name}</div>
            </div>
            
            <div class="info-row">
                <div class="label">Severity</div>
                <div class="value">
                    <span class="severity-badge">{payload.severity.upper()}</span>
                </div>
            </div>
            
            <div class="info-row">
                <div class="label">Title</div>
                <div class="value">{payload.title}</div>
            </div>
            
            <div class="info-row">
                <div class="label">Time</div>
                <div class="value">{payload.timestamp}</div>
            </div>
            
            <div class="message-box">
                <div class="label">Details</div>
                <div class="value">{payload.message}</div>
            </div>
            
            {f'<a href="{payload.monitor_url}" class="button">View Monitor</a>' if payload.monitor_url else ''}
        </div>
        <div class="footer">
            This is an automated alert from your monitoring system.
        </div>
    </div>
</body>
</html>
"""

    def _create_plain_body(self, payload: AlertPayload) -> str:
        """Create plain text email body."""
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 MONITOR ALERT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Monitor: {payload.monitor_name}
Severity: {payload.severity.upper()}
Time: {payload.timestamp}

Title: {payload.title}

Details:
{payload.message}

{f"Monitor URL: {payload.monitor_url}" if payload.monitor_url else ""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is an automated alert from your monitoring system.
"""

    async def send(self, payload: AlertPayload) -> bool:
        """
        Send alert email asynchronously.

        Args:
            payload: Alert data to send

        Returns:
            True if successful, False otherwise
        """
        if not self.validate_config():
            return False

        try:
            # Run synchronous SMTP operations in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._send_sync, payload)
            return result

        except Exception as exc:
            logger.error(
                "email_alert_failed",
                error=str(exc),
                exc_info=True,
            )
            return False

    def _send_sync(self, payload: AlertPayload) -> bool:
        """
        Synchronous email sending (called from executor).

        Args:
            payload: Alert data to send

        Returns:
            True if successful, False otherwise
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            msg["Subject"] = f"[{payload.severity.upper()}] {payload.title}"

            # Create plain text version
            plain_body = self._create_plain_body(payload)
            msg.attach(MIMEText(plain_body, "plain"))

            # Create HTML version if enabled
            if self.use_html:
                html_body = self._create_html_body(payload)
                msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(
                self.smtp_host, self.smtp_port, timeout=self.timeout
            ) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(
                "email_alert_sent",
                to_emails=self.to_emails,
                monitor=payload.monitor_name,
                severity=payload.severity,
            )
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error(
                "email_authentication_failed",
                smtp_host=self.smtp_host,
                smtp_user=self.smtp_user,
            )
            return False

        except smtplib.SMTPException as exc:
            logger.error(
                "smtp_error",
                error=str(exc),
                smtp_host=self.smtp_host,
            )
            return False

        except Exception as exc:
            logger.error(
                "email_send_failed",
                error=str(exc),
                exc_info=True,
            )
            return False

    async def test_connection(self) -> bool:
        """
        Test SMTP connection and authentication.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._test_connection_sync)
        except Exception as exc:
            logger.error("email_test_failed", error=str(exc))
            return False

    def _test_connection_sync(self) -> bool:
        """Synchronous connection test."""
        try:
            with smtplib.SMTP(
                self.smtp_host, self.smtp_port, timeout=self.timeout
            ) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
            logger.info("email_connection_test_passed")
            return True
        except Exception as exc:
            logger.error("email_connection_test_failed", error=str(exc))
            return False
