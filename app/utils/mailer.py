import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def mail_is_configured() -> bool:
    """True once SMTP_HOST and SMTP_FROM are set in the environment/config."""
    cfg = current_app.config
    return bool(cfg.get("SMTP_HOST") and cfg.get("SMTP_FROM"))


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Send a plain-text email via SMTP using the app's configured settings.

    Returns True if the message was handed off to the SMTP server, False if
    SMTP isn't configured (caller should fall back to logging in that case).
    Raises on an actual SMTP failure (bad credentials, connection refused,
    etc.) so callers/logs surface real delivery problems.
    """
    cfg = current_app.config
    if not mail_is_configured():
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["SMTP_FROM"]
    msg["To"] = to
    msg.set_content(body)

    host = cfg["SMTP_HOST"]
    port = int(cfg.get("SMTP_PORT", 587))
    username = cfg.get("SMTP_USERNAME")
    password = cfg.get("SMTP_PASSWORD")
    use_ssl = bool(cfg.get("SMTP_USE_SSL"))

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as server:
            if username:
                server.login(username, password or "")
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as server:
            if cfg.get("SMTP_USE_TLS", True):
                server.starttls(context=ssl.create_default_context())
            if username:
                server.login(username, password or "")
            server.send_message(msg)

    return True


def send_password_reset_email(to: str, username: str, raw_token: str, ttl_minutes: int) -> bool:
    """Compose and send the password reset email. See send_email() for the
    return/raise contract."""
    reset_url_base = current_app.config.get("PASSWORD_RESET_URL_BASE")
    link_line = f"{reset_url_base.rstrip('/')}/{raw_token}\n\n" if reset_url_base else ""

    subject = "Password reset request"
    body = (
        f"Hello {username},\n\n"
        "A password reset was requested for your account.\n\n"
        f"{link_line}"
        f"Reset token: {raw_token}\n"
        f"This token expires in {ttl_minutes} minutes.\n\n"
        "If you didn't request this, you can safely ignore this email."
    )
    return send_email(to, subject, body)