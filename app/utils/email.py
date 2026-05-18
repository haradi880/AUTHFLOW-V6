import html
import re
import threading

from flask import current_app, render_template

from app.utils.emailer import send_email as deliver_email


def _html_to_text(markup):
    text = re.sub(r"<br\s*/?>", "\n", markup, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def send_async_email(app, subject, recipient, text_body, html_body):
    with app.app_context():
        deliver_email(recipient, subject, text_body, html_body=html_body)


def send_email(subject, recipient, template, **kwargs):
    """Send a rendered HTML email through the shared delivery chain."""
    app = current_app._get_current_object()

    try:
        html_body = render_template(f"email/{template}.html", **kwargs)
    except Exception:
        html_body = kwargs.get("body", "Notification from AuthFlow")
    text_body = kwargs.get("text_body") or _html_to_text(html_body)

    if not app.config.get("EMAIL_ASYNC", True) or app.config.get("MAIL_SUPPRESS_SEND"):
        return deliver_email(recipient, subject, text_body, html_body=html_body)

    thread = threading.Thread(target=send_async_email, args=(app, subject, recipient, text_body, html_body), daemon=True)
    thread.start()
    return True
