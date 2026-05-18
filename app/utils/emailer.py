"""Email delivery helpers with SMTP and API fallbacks."""

import json
import re
import smtplib
import socket
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app


class EmailDeliveryError(RuntimeError):
    """Raised when a configured email backend cannot deliver."""


class _SMTPIPv4(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return _create_ipv4_connection(host, port, timeout, self.source_address)


class _SMTPSSLIPv4(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        raw_socket = _create_ipv4_connection(host, port, timeout, self.source_address)
        return self.context.wrap_socket(raw_socket, server_hostname=host)


def _create_ipv4_connection(host, port, timeout, source_address=None):
    last_error = None
    for family, socktype, proto, _, address in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(address)
            return sock
        except OSError as exc:
            last_error = exc
            if sock is not None:
                sock.close()
    raise last_error or OSError(f"Could not connect to {host}:{port} over IPv4")


def _sender_email(sender):
    _, email = parseaddr(sender or "")
    return email or sender


def _sender_name(sender):
    name, _ = parseaddr(sender or "")
    return name or current_app.config.get("MAIL_SENDER_NAME", "AuthFlow")


def _format_sender(sender):
    name, email = parseaddr(sender or "")
    if name and email:
        return sender
    sender = sender or current_app.config.get("MAIL_DEFAULT_SENDER") or "noreply@example.com"
    return formataddr((current_app.config.get("MAIL_SENDER_NAME", "AuthFlow"), sender))


def _build_message(to_email, subject, body, html_body=None, sender=None):
    sender = sender or current_app.config.get("MAIL_DEFAULT_SENDER")
    msg = EmailMessage()
    msg["From"] = _format_sender(sender)
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body or "")
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg


def _smtp_settings(prefix):
    return {
        "server": current_app.config.get(f"{prefix}_SERVER"),
        "port": int(current_app.config.get(f"{prefix}_PORT") or 0),
        "use_tls": bool(current_app.config.get(f"{prefix}_USE_TLS")),
        "use_ssl": bool(current_app.config.get(f"{prefix}_USE_SSL")),
        "username": current_app.config.get(f"{prefix}_USERNAME"),
        "password": current_app.config.get(f"{prefix}_PASSWORD"),
        "sender": current_app.config.get(f"{prefix}_DEFAULT_SENDER") or current_app.config.get("MAIL_DEFAULT_SENDER"),
        "timeout": float(current_app.config.get("MAIL_TIMEOUT", 10)),
        "force_ipv4": bool(current_app.config.get("MAIL_FORCE_IPV4")),
    }


def _send_smtp(msg, settings):
    if not settings["server"] or not settings["port"]:
        raise EmailDeliveryError("SMTP server or port is not configured.")
    if not settings["username"] or not settings["password"]:
        raise EmailDeliveryError("SMTP username or password is not configured.")

    use_ssl = settings["use_ssl"] or settings["port"] == 465
    use_tls = settings["use_tls"] and not use_ssl
    context = ssl.create_default_context()

    if settings["force_ipv4"]:
        smtp_cls = _SMTPSSLIPv4 if use_ssl else _SMTPIPv4
    else:
        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

    if use_ssl:
        server = smtp_cls(settings["server"], settings["port"], timeout=settings["timeout"], context=context)
    else:
        server = smtp_cls(settings["server"], settings["port"], timeout=settings["timeout"])

    with server:
        server.ehlo()
        if use_tls:
            server.starttls(context=context)
            server.ehlo()
        server.login(settings["username"], settings["password"])
        server.send_message(msg)


def _post_json(url, payload, headers, timeout, accepted_statuses):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status not in accepted_statuses:
                detail = response.read(500).decode("utf-8", errors="replace")
                raise EmailDeliveryError(f"HTTP {response.status}: {detail}")
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise EmailDeliveryError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise EmailDeliveryError(str(exc.reason)) from exc


def _send_resend(to_email, subject, body, html_body=None):
    api_key = current_app.config.get("RESEND_API_KEY")
    sender = current_app.config.get("RESEND_FROM") or current_app.config.get("MAIL_DEFAULT_SENDER")
    if not api_key:
        raise EmailDeliveryError("RESEND_API_KEY is not configured.")

    payload = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "text": body or "",
    }
    if html_body:
        payload["html"] = html_body

    _post_json(
        "https://api.resend.com/emails",
        payload,
        {"Authorization": f"Bearer {api_key}"},
        float(current_app.config.get("MAIL_TIMEOUT", 10)),
        {200, 202},
    )


def _send_sendgrid(to_email, subject, body, html_body=None):
    api_key = current_app.config.get("SENDGRID_API_KEY")
    sender = current_app.config.get("SENDGRID_FROM") or current_app.config.get("MAIL_DEFAULT_SENDER")
    if not api_key:
        raise EmailDeliveryError("SENDGRID_API_KEY is not configured.")

    content = [{"type": "text/plain", "value": body or ""}]
    if html_body:
        content.append({"type": "text/html", "value": html_body})

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": _sender_email(sender), "name": _sender_name(sender)},
        "subject": subject,
        "content": content,
    }
    _post_json(
        "https://api.sendgrid.com/v3/mail/send",
        payload,
        {"Authorization": f"Bearer {api_key}"},
        float(current_app.config.get("MAIL_TIMEOUT", 10)),
        {200, 202},
    )


def _write_outbox(msg):
    outbox = Path(current_app.config.get("EMAIL_OUTBOX_FOLDER", "logs/email_outbox"))
    if not outbox.is_absolute():
        outbox = Path(current_app.root_path).parent / outbox
    outbox.mkdir(parents=True, exist_ok=True)
    safe_to = re.sub(r"[^A-Za-z0-9_.@-]+", "_", msg["To"])[:80]
    filename = f"{datetime.utcnow():%Y%m%d%H%M%S%f}_{safe_to}.eml"
    path = outbox / filename
    path.write_text(msg.as_string(), encoding="utf-8")
    current_app.logger.warning("Email saved to local outbox fallback: %s", path)


def _delivery_order():
    backend = (current_app.config.get("EMAIL_BACKEND") or "auto").lower()
    if backend != "auto":
        return [backend]

    raw_order = current_app.config.get("EMAIL_DELIVERY_ORDER") or "smtp,backup_smtp,resend,sendgrid,file"
    order = [item.strip().lower() for item in raw_order.split(",") if item.strip()]
    if not current_app.config.get("EMAIL_FILE_FALLBACK"):
        order = [item for item in order if item != "file"]
    return order


def send_email(to_email, subject, body, html_body=None):
    """Send an email through configured backends without crashing the request."""
    if current_app.config.get("MAIL_SUPPRESS_SEND"):
        current_app.logger.info("Email suppressed to=%s subject=%s", to_email, subject)
        return True

    errors = []
    order = _delivery_order()
    current_app.logger.info("Email delivery started to=%s subject=%s backends=%s", to_email, subject, ",".join(order))

    for backend in order:
        try:
            if backend == "smtp":
                msg = _build_message(to_email, subject, body, html_body, current_app.config.get("MAIL_DEFAULT_SENDER"))
                _send_smtp(msg, _smtp_settings("MAIL"))
            elif backend == "backup_smtp":
                msg = _build_message(to_email, subject, body, html_body, current_app.config.get("MAIL_BACKUP_DEFAULT_SENDER"))
                _send_smtp(msg, _smtp_settings("MAIL_BACKUP"))
            elif backend == "resend":
                _send_resend(to_email, subject, body, html_body)
            elif backend == "sendgrid":
                _send_sendgrid(to_email, subject, body, html_body)
            elif backend == "file":
                msg = _build_message(to_email, subject, body, html_body)
                _write_outbox(msg)
            else:
                raise EmailDeliveryError(f"Unknown email backend: {backend}")

            current_app.logger.info("Email delivered to=%s subject=%s backend=%s", to_email, subject, backend)
            return True
        except Exception as exc:
            errors.append(f"{backend}: {exc}")
            current_app.logger.warning("Email backend failed to=%s backend=%s error=%s", to_email, backend, exc)

    current_app.logger.error("Email delivery failed to=%s subject=%s errors=%s", to_email, subject, " | ".join(errors))
    return False


def send_otp_email(email, otp):
    """Send OTP verification code to user's email."""
    subject = "Your Verification Code - AuthFlow"
    body = f"""
Hello!

Your verification code is: {otp}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.

Best regards,
AuthFlow Team
"""
    return send_email(email, subject, body)


def send_welcome_email(email, username):
    """Send welcome email to new users."""
    subject = "Welcome to AuthFlow!"
    body = f"""
Hello {username}!

Welcome to AuthFlow - the developer blogging platform.

You can now:
- Write and publish blog posts
- Share your projects
- Follow other developers
- Build your portfolio

Get started by writing your first blog post!

Best regards,
AuthFlow Team
"""
    return send_email(email, subject, body)
