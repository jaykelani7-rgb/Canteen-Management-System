"""SMTP delivery uses verified TLS and never writes recovery codes to logs."""
import asyncio
from email.message import EmailMessage
from email.utils import parseaddr
import smtplib
import ssl
from config import settings


class DeliveryUnavailable(Exception):
    pass


def valid_contact_email(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 254 or any(c in value for c in "\r\n"):
        return False
    try:
        value.encode("ascii")
        address = parseaddr(value)[1]
    except (ValueError, UnicodeError):
        return False
    return address == value and address.count("@") == 1 and bool(address.split("@")[0]) and "." in address.split("@")[1]


def recovery_delivery_configured() -> bool:
    return bool(settings.PASSCODE_RECOVERY_ENABLED and settings.SMTP_HOST
                and valid_contact_email(settings.SMTP_FROM_EMAIL)
                and settings.SMTP_SECURITY in {"starttls", "ssl"}
                and bool(settings.SMTP_USERNAME) == bool(settings.SMTP_PASSWORD))


def _send(recipient: str, code: str, ttl_seconds: int) -> None:
    if not recovery_delivery_configured() or not valid_contact_email(recipient):
        raise DeliveryUnavailable("Recovery delivery is unavailable")
    message = EmailMessage()
    message["Subject"] = "Smart Canteen passcode recovery"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message.set_content(
        "Your Smart Canteen recovery code is: " + code + "\n\n"
        + "It expires in " + str(max(1, ttl_seconds // 60)) + " minutes and can be used once.\n"
        + "If you did not request this code, ignore this email. Do not share the code.\n"
    )
    context = ssl.create_default_context()
    try:
        if settings.SMTP_SECURITY == "ssl":
            connection = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                                          timeout=settings.SMTP_TIMEOUT_SECONDS, context=context)
        else:
            connection = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT,
                                      timeout=settings.SMTP_TIMEOUT_SECONDS)
        with connection as smtp:
            smtp.ehlo()
            if settings.SMTP_SECURITY == "starttls":
                smtp.starttls(context=context)
                smtp.ehlo()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException, ssl.SSLError):
        # SMTP exceptions may include addresses or server details; discard them.
        raise DeliveryUnavailable("Recovery delivery is unavailable") from None


async def send_recovery_code(recipient: str, code: str, ttl_seconds: int) -> None:
    try:
        await asyncio.wait_for(asyncio.to_thread(_send, recipient, code, ttl_seconds),
                               timeout=settings.SMTP_TIMEOUT_SECONDS * 2)
    except (TimeoutError, DeliveryUnavailable):
        raise DeliveryUnavailable("Recovery delivery is unavailable") from None
