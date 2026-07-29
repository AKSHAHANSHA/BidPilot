"""Transactional mail: one protocol, two transports, and a factory that records which ran.

Exactly one message matters in this phase — the password-reset link — and delivery is the part
of that flow most likely to be wrong in any given environment. So it sits behind a protocol for
the same reason storage does (`app/storage/base.py`): development, a hosted demo, and tests each
need a different answer, and none of them should require changing the service that sends.

:class:`LogMailer` is the default and it is a *real* transport, not a stub. In development it
writes the whole rendered message at INFO so a developer can copy the reset link straight out of
the console without any SMTP credentials at all — the flow is genuinely usable with the shipped
configuration. Outside development it writes everything except the body, at WARNING, because a
reset link is a bearer credential that must not sit in a deployed environment's log and because
`MAIL_TRANSPORT=log` in a deployed environment means reset mail is reaching nobody — a
misconfiguration that deserves to be loud rather than silent.

Delivery failure raises :class:`MailDeliveryError` and nothing else. The caller decides what a
failure means; for password reset it must not change the response, because an endpoint that
errors only for registered addresses is the enumeration oracle the flow exists to avoid.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Final, Protocol

from app.core.config import ConfigurationError, Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

LOG_TRANSPORT: Final = "log"
SMTP_TRANSPORT: Final = "smtp"

#: Bound on one SMTP conversation. A relay that stops responding must fail the request rather
#: than hold a worker thread — and, on password reset, rather than stretch the response time
#: for registered addresses into a signal.
SMTP_TIMEOUT_SECONDS: Final = 30.0


class MailDeliveryError(RuntimeError):
    """The message could not be handed to its transport.

    Carries a transport-level summary for the log, never the server's own reply text: an SMTP
    rejection commonly quotes the recipient address back, and that address is the thing a
    password-reset probe is trying to learn.
    """


class Mailer(Protocol):
    async def send(self, *, to: str, subject: str, text_body: str) -> None:
        """Deliver one plain-text message.

        Plain text only, deliberately: the messages this system sends are short and
        transactional, and an HTML body would be one more place for a link to be rewritten or
        mangled between here and the user.

        Raises :class:`MailDeliveryError` when the transport refuses or fails.
        """
        ...


def mask_address(address: str) -> str:
    """``c***@fm-demo.ae`` — enough to recognise a recipient in a log without recording them.

    An address is personal data, and in a password-reset flow it is also the account
    identifier; a log aggregator is not the place to accumulate either.
    """
    local, separator, domain = address.partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


def _reject_header_injection(field: str, value: str) -> str:
    """Refuse a header value carrying a line break.

    Every value reaching a header here is server-generated or a validated stored address, so
    this should be unreachable. It stays because the failure mode if it ever is reachable —
    a smuggled `Bcc:` — is silent, and one comparison is a cheap way to keep it impossible.
    """
    if "\n" in value or "\r" in value:
        raise MailDeliveryError(f"{field} header contains a line break")
    return value


class LogMailer:
    """Delivery by structured log line. The default transport.

    See the module docstring for why this is a real transport and why it goes quiet outside
    development. It never raises: writing a log line cannot fail in a way the caller could act
    on differently.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, *, to: str, subject: str, text_body: str) -> None:
        if self._settings.is_development:
            logger.info(
                "mail_delivered",
                extra={
                    "transport": LOG_TRANSPORT,
                    "to": to,
                    "subject": subject,
                    # The rendered message, link and all. Development only — see the module
                    # docstring. `body` rather than `message`, which `logging` reserves.
                    "body": text_body,
                },
            )
            return

        logger.warning(
            "mail_not_delivered",
            extra={
                "transport": LOG_TRANSPORT,
                "to": mask_address(to),
                "subject": subject,
                "body_chars": len(text_body),
                "reason": "log_transport_outside_development",
            },
        )


class SmtpMailer:
    """Delivery over SMTP using the standard library.

    `smtplib` is synchronous, so the whole conversation runs in a worker thread exactly as
    boto3 does in `app/storage/s3.py`; a slow relay never blocks the event loop. No dependency
    is added for this — an SMTP submission is a handful of lines and a third-party client would
    buy nothing but another thing to keep current.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # `build_mailer` is the only sanctioned constructor and it rejects a missing host, so
        # this can only be empty when something bypassed the factory.
        self._host = settings.smtp_host or ""

    async def send(self, *, to: str, subject: str, text_body: str) -> None:
        message = self._build_message(to=to, subject=subject, text_body=text_body)
        try:
            await asyncio.to_thread(self._deliver, message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.error(
                "mail_delivery_failed",
                extra={
                    "transport": SMTP_TRANSPORT,
                    "to": mask_address(to),
                    # Type only: the exception text carries the server's reply, which routinely
                    # quotes the recipient address.
                    "error": type(exc).__name__,
                },
            )
            raise MailDeliveryError(f"SMTP delivery failed: {type(exc).__name__}") from exc

        logger.info(
            "mail_delivered",
            extra={"transport": SMTP_TRANSPORT, "to": mask_address(to), "subject": subject},
        )

    def _build_message(self, *, to: str, subject: str, text_body: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = formataddr(
            (self._settings.mail_from_name, self._settings.mail_from_address)
        )
        message["To"] = _reject_header_injection("To", to)
        message["Subject"] = _reject_header_injection("Subject", subject)
        message.set_content(text_body)
        return message

    def _deliver(self, message: EmailMessage) -> None:
        """Blocking submission. Runs in a worker thread; never call it from the event loop."""
        settings = self._settings
        with smtplib.SMTP(self._host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as client:
            if settings.smtp_use_tls:
                client.ehlo()
                # The context is passed explicitly: `starttls()` with no argument builds one
                # that neither verifies the certificate nor checks the hostname, which makes
                # the encryption decorative against anyone positioned to intercept it.
                client.starttls(context=ssl.create_default_context())
                # Re-greet: the server's capability list is renegotiated after TLS, and AUTH is
                # commonly advertised only inside it.
                client.ehlo()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)


def build_mailer(settings: Settings) -> Mailer:
    """Choose the transport and record the choice.

    A mail that never arrives is investigated from the logs, so which transport was selected —
    and, when it is the quiet one, why — is written at selection time rather than left to be
    inferred from its absence.
    """
    if settings.mail_transport == SMTP_TRANSPORT:
        if not settings.smtp_host:
            # Fail here rather than on the first reset request: a deployment missing its relay
            # host is a startup problem, and discovering it through an unsent password reset
            # is the most expensive possible way to find out.
            raise ConfigurationError("MAIL_TRANSPORT=smtp requires SMTP_HOST to be set")
        logger.info(
            "mail_transport_selected",
            extra={
                "transport": SMTP_TRANSPORT,
                "host": settings.smtp_host,
                "port": settings.smtp_port,
                "use_tls": settings.smtp_use_tls,
            },
        )
        return SmtpMailer(settings)

    if not settings.is_development:
        logger.warning(
            "mail_transport_selected",
            extra={"transport": LOG_TRANSPORT, "reason": "log_transport_outside_development"},
        )
    else:
        logger.info("mail_transport_selected", extra={"transport": LOG_TRANSPORT})
    return LogMailer(settings)
