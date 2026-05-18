import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app, render_template


def send_async_email(app, msg, settings):
    with app.app_context():
        try:
            with smtplib.SMTP(settings["server"], settings["port"]) as server:
                if settings["use_tls"]:
                    server.starttls()
                if settings["username"] and settings["password"]:
                    server.login(settings["username"], settings["password"])
                server.send_message(msg)
            current_app.logger.info("Email sent successfully to %s", msg["To"])
        except Exception as exc:
            current_app.logger.warning("Error sending email: %s", exc)


def send_email(subject, recipient, template, **kwargs):
    """Send an HTML email, or log a mock email when SMTP credentials are absent."""
    app = current_app._get_current_object()
    settings = {
        "server": app.config.get("MAIL_SERVER"),
        "port": app.config.get("MAIL_PORT"),
        "use_tls": app.config.get("MAIL_USE_TLS"),
        "username": app.config.get("MAIL_USERNAME"),
        "password": app.config.get("MAIL_PASSWORD"),
        "sender": app.config.get("MAIL_DEFAULT_SENDER"),
    }

    try:
        body = render_template(f"email/{template}.html", **kwargs)
    except Exception:
        body = kwargs.get("body", "Notification from AuthFlow")

    msg = MIMEMultipart()
    msg["From"] = settings["sender"]
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    if not settings["username"] or not settings["password"]:
        app.logger.info("Mock email to=%s subject=%s body=%s...", recipient, subject, body[:100])
        return

    thread = threading.Thread(target=send_async_email, args=(app, msg, settings), daemon=True)
    thread.start()
