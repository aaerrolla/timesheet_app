"""
Email delivery service.

If SMTP_HOST is not configured, emails are logged to the console and to
outbox/outbox.log instead of being sent, so the app is usable with zero
mail-server configuration -- see README.md for the SMTP_* environment
variables that enable real delivery.
"""
import logging
import os
import secrets
import smtplib
import string
from datetime import datetime
from email.mime.text import MIMEText

from config import OUTBOX_DIR

logger = logging.getLogger("timesheet.email")


def generate_temp_password(length=10):
    # Exclude visually-confusing characters (0/O, 1/l/I) from a temp password
    # someone has to read out of an email or a console log and type in.
    alphabet = "".join(c for c in (string.ascii_letters + string.digits) if c not in "0O1lI")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _append_outbox(to_email, subject, body, error=None):
    os.makedirs(OUTBOX_DIR, exist_ok=True)
    path = os.path.join(OUTBOX_DIR, "outbox.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.utcnow().isoformat()}Z =====\n")
        f.write(f"To: {to_email}\nSubject: {subject}\n")
        if error:
            f.write(f"SEND ERROR: {error}\n")
        f.write(f"\n{body}\n")


def send_email(to_email, subject, body):
    """
    Send an email if SMTP_HOST is configured; otherwise log it to the console
    and to outbox/outbox.log so the app remains usable without a mail server.
    Returns True if a real send was attempted and succeeded, False otherwise.
    """
    host = os.environ.get("SMTP_HOST")
    if not host:
        logger.info(
            "SMTP not configured -- logging email instead of sending.\nTo: %s\nSubject: %s\n\n%s",
            to_email, subject, body,
        )
        _append_outbox(to_email, subject, body)
        return False

    port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM") or smtp_user or "no-reply@timesheet.local"
    use_tls = os.environ.get("SMTP_USE_TLS", "1") != "0"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(sender, [to_email], msg.as_string())
        return True
    except Exception as exc:  # noqa: BLE001 - we want to swallow & log any SMTP failure
        logger.error("Failed to send email to %s: %s", to_email, exc)
        _append_outbox(to_email, subject, body, error=str(exc))
        return False
