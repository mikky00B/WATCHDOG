from __future__ import annotations

import html

import httpx
import structlog

from monitoring.alerting.addressing import format_from_address
from monitoring.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class TransactionalEmailSender:
    """Send non-alert account emails such as verification and password reset codes."""

    def __init__(self, settings: Settings | None = None, timeout: int = 30):
        self.settings = settings or get_settings()
        self.timeout = timeout
        self.last_error: str | None = None

    async def send_verification_code(self, to_email: str, code: str, expires_minutes: int) -> bool:
        return await self._send_code_email(
            to_email=to_email,
            subject="Verify your WATCHDOG email",
            heading="Verify your email",
            intro="Use this code to finish creating your WATCHDOG account.",
            code=code,
            expires_minutes=expires_minutes,
            footer="If you did not create a WATCHDOG account, you can ignore this email.",
        )

    async def send_password_reset_code(self, to_email: str, code: str, expires_minutes: int) -> bool:
        return await self._send_code_email(
            to_email=to_email,
            subject="Reset your WATCHDOG password",
            heading="Reset your password",
            intro="Use this code to reset your WATCHDOG password.",
            code=code,
            expires_minutes=expires_minutes,
            footer="If you did not request a password reset, you can ignore this email.",
        )

    async def _send_code_email(
        self,
        to_email: str,
        subject: str,
        heading: str,
        intro: str,
        code: str,
        expires_minutes: int,
        footer: str,
    ) -> bool:
        if not self._validate_config(to_email):
            return False
        plain_body = self._plain_code_body(heading, intro, code, expires_minutes, footer)
        html_body = self._html_code_body(heading, intro, code, expires_minutes, footer)
        return await self._send(to_email, subject, plain_body, html_body)

    def _validate_config(self, to_email: str) -> bool:
        self.last_error = None
        if not all(
            [
                self.settings.resend_api_key,
                self.settings.from_email,
                to_email,
            ]
        ):
            self.last_error = "Resend email configuration is incomplete"
            return False
        return True

    async def _send(self, to_email: str, subject: str, plain_body: str, html_body: str) -> bool:
        try:
            from_email = str(self.settings.from_email or "")
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self.settings.resend_api_key}"},
                    json={
                        "from": format_from_address(from_email, self.settings.from_name),
                        "to": [to_email],
                        "subject": subject,
                        "text": plain_body,
                        "html": html_body,
                    },
                )
                response.raise_for_status()
            logger.info("transactional_email_sent", to_email=to_email, subject=subject)
            return True
        except httpx.HTTPStatusError as exc:
            self.last_error = f"Resend API error ({exc.response.status_code}): {exc.response.text}"
            logger.error(
                "transactional_email_resend_api_error",
                status_code=exc.response.status_code,
                response=exc.response.text,
            )
            return False
        except httpx.HTTPError as exc:
            self.last_error = f"Resend HTTP error: {exc}"
            logger.error("transactional_email_resend_http_error", error=str(exc))
            return False
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("transactional_email_failed", error=str(exc), exc_info=True)
            return False

    @staticmethod
    def _plain_code_body(
        heading: str,
        intro: str,
        code: str,
        expires_minutes: int,
        footer: str,
    ) -> str:
        return (
            f"{heading}\n\n"
            f"{intro}\n\n"
            f"Code: {code}\n"
            f"Expires in: {expires_minutes} minutes\n\n"
            f"{footer}\n"
        )

    @staticmethod
    def _html_code_body(
        heading: str,
        intro: str,
        code: str,
        expires_minutes: int,
        footer: str,
    ) -> str:
        safe_heading = html.escape(heading)
        safe_intro = html.escape(intro)
        safe_footer = html.escape(footer)
        safe_code = html.escape(code)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_heading}</title>
</head>
<body style="margin:0;background:#f5f7fb;color:#172033;font-family:Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f7fb;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:#ffffff;border:1px solid #d8dee9;border-radius:8px;overflow:hidden;">
          <tr>
            <td style="padding:28px 32px 16px;">
              <div style="font-size:13px;font-weight:700;letter-spacing:.08em;color:#52606d;">WATCHDOG</div>
              <h1 style="margin:12px 0 8px;font-size:24px;line-height:1.25;color:#172033;">{safe_heading}</h1>
              <p style="margin:0;color:#52606d;font-size:15px;line-height:1.6;">{safe_intro}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 32px 24px;">
              <div style="background:#eef4ff;border:1px solid #c7d7fe;border-radius:8px;padding:22px;text-align:center;">
                <div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#52606d;text-transform:uppercase;">Verification code</div>
                <div style="font-size:36px;font-weight:800;letter-spacing:.18em;color:#1e3a8a;margin-top:8px;">{safe_code}</div>
                <div style="font-size:13px;color:#52606d;margin-top:10px;">Expires in {expires_minutes} minutes</div>
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:0 32px 28px;">
              <p style="margin:0;color:#52606d;font-size:13px;line-height:1.6;">{safe_footer}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
