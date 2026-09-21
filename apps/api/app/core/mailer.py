"""Outbound email over SMTP.

There is deliberately no third-party provider SDK here: every transactional provider (SES,
Postmark, SendGrid, Resend, Mailgun, Gmail with an app password) exposes SMTP, so one set of
`SMTP_*` settings covers all of them. Sending runs in a worker thread so the event loop is
never blocked by a slow relay.

`send()` never raises. It returns a `Delivery` that says whether the message left the server
and, if not, *why* — callers surface that to the user instead of pretending it was sent.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import get_settings

log = logging.getLogger(__name__)

NOT_CONFIGURED = (
    "Email is not configured on this server. Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, "
    "SMTP_PASSWORD and SMTP_FROM in apps/api/.env (any provider that offers SMTP works: "
    "Amazon SES, Postmark, SendGrid, Resend, Mailgun, or Gmail with an app password)."
)


@dataclass(frozen=True)
class Delivery:
    sent: bool
    error: str | None = None
    """Human-readable reason when `sent` is False."""

    @staticmethod
    def ok() -> Delivery:
        return Delivery(sent=True)

    @staticmethod
    def failed(reason: str) -> Delivery:
        return Delivery(sent=False, error=reason)


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from)


def _build(to: str, subject: str, text: str, html: str | None) -> EmailMessage:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def _deliver_sync(msg: EmailMessage) -> None:
    """Blocking SMTP round-trip. STARTTLS on 587 by default, implicit TLS when SMTP_SSL=true."""
    settings = get_settings()
    timeout = settings.smtp_timeout_seconds
    context = ssl.create_default_context()
    if settings.smtp_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with client:
        client.ehlo()
        if not settings.smtp_ssl and settings.smtp_starttls:
            client.starttls(context=context)
            client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(msg)


async def send(to: str, subject: str, text: str, html: str | None = None) -> Delivery:
    """Send one message. Returns a Delivery describing what actually happened."""
    settings = get_settings()
    if not is_configured():
        return Delivery.failed(NOT_CONFIGURED)
    msg = _build(to, subject, text, html)
    try:
        await asyncio.to_thread(_deliver_sync, msg)
    except smtplib.SMTPAuthenticationError as e:
        log.warning("smtp auth failed: %s", e)
        return Delivery.failed(
            "The email server rejected the SMTP username/password. Check SMTP_USERNAME and "
            "SMTP_PASSWORD (Gmail needs an app password, not the account password)."
        )
    except smtplib.SMTPRecipientsRefused as e:
        log.warning("smtp recipient refused: %s", e)
        return Delivery.failed(f"The email server refused the address {to}.")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        log.warning("smtp send failed: %s", e)
        return Delivery.failed(
            f"Could not reach the email server at {settings.smtp_host}:{settings.smtp_port} "
            f"({e.__class__.__name__}: {e}). Check SMTP_HOST, SMTP_PORT and SMTP_STARTTLS/SMTP_SSL."
        )
    log.info("email sent", extra={"to": to, "subject": subject})
    return Delivery.ok()
