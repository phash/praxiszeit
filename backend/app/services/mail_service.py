"""SMTP mail delivery (Phase 3 / Issue #94).

Kept minimal and stdlib-only so we don't pull in FastMail/MailHog for a
single transactional mail flow. If SMTP credentials are missing the
service logs the email body instead of raising — letting the signup flow
succeed locally and in CI without a relay configured. Production MUST
set MAIL_HOST + MAIL_FROM; the ``is_configured`` helper is used by
``/api/system/info`` callers that need to know whether real delivery
happens.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import settings


logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(getattr(settings, "MAIL_HOST", None)) and bool(
        getattr(settings, "MAIL_FROM", None)
    )


class MailService:
    """Thin wrapper around smtplib. Sends one transactional mail per call."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        from_addr: Optional[str] = None,
        starttls: Optional[bool] = None,
    ):
        self.host = host if host is not None else getattr(settings, "MAIL_HOST", None)
        self.port = port if port is not None else getattr(settings, "MAIL_PORT", 587)
        self.user = user if user is not None else getattr(settings, "MAIL_USER", None)
        self.password = password if password is not None else getattr(settings, "MAIL_PASS", None)
        self.from_addr = from_addr if from_addr is not None else getattr(settings, "MAIL_FROM", None)
        self.starttls = starttls if starttls is not None else getattr(settings, "MAIL_STARTTLS", True)

    def send(self, *, to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
        """Send a single email. Returns True on success (or dry-run)."""
        if not self.host or not self.from_addr:
            # Dry-run: log so signup tests / local dev can assert on content
            # without a relay configured. Contains the verification URL.
            logger.info(
                "mail_service dry-run (no SMTP configured): to=%s subject=%r body=%s",
                to, subject, body_text,
            )
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = to
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.ehlo()
                if self.starttls:
                    smtp.starttls()
                    smtp.ehlo()
                if self.user and self.password:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
            return True
        except Exception as exc:  # noqa: BLE001 — smtp errors are varied
            logger.exception("mail_service: failed to send to %s: %s", to, exc)
            return False


def send_verification_email(to: str, verification_url: str, practice_name: str) -> bool:
    """Composed signup-verification email. Called from the signup endpoint."""
    subject = "Bitte E-Mail-Adresse bestätigen – PraxisZeit"
    body_text = (
        f"Hallo,\n\n"
        f"vielen Dank für die Registrierung von '{practice_name}' bei PraxisZeit.\n\n"
        f"Bitte bestätige deine E-Mail-Adresse über folgenden Link (24 Stunden gültig):\n\n"
        f"{verification_url}\n\n"
        f"Wenn du diese Registrierung nicht angefordert hast, kannst du diese E-Mail ignorieren.\n\n"
        f"Viele Grüße\nDein PraxisZeit-Team"
    )
    body_html = (
        f"<p>Hallo,</p>"
        f"<p>vielen Dank für die Registrierung von <strong>{practice_name}</strong> bei PraxisZeit.</p>"
        f"<p>Bitte bestätige deine E-Mail-Adresse über folgenden Link (24 Stunden gültig):</p>"
        f'<p><a href="{verification_url}">{verification_url}</a></p>'
        f"<p>Wenn du diese Registrierung nicht angefordert hast, kannst du diese E-Mail ignorieren.</p>"
        f"<p>Viele Grüße<br>Dein PraxisZeit-Team</p>"
    )
    return MailService().send(to=to, subject=subject, body_text=body_text, body_html=body_html)
