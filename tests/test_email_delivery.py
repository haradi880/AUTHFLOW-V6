from app import create_app
from app.utils.emailer import EmailDeliveryError, send_email


def test_email_uses_api_fallback_after_smtp_failure(monkeypatch):
    app = create_app("testing")
    app.config.update(
        EMAIL_BACKEND="auto",
        MAIL_SUPPRESS_SEND=False,
        EMAIL_DELIVERY_ORDER="smtp,resend",
        RESEND_API_KEY="test-key",
        RESEND_FROM="HaradiBots <noreply@example.com>",
        MAIL_USERNAME="smtp-user",
        MAIL_PASSWORD="smtp-password",
    )
    delivered = []

    def fail_smtp(msg, settings):
        raise EmailDeliveryError("network is unreachable")

    def fake_resend(to_email, subject, body, html_body=None):
        delivered.append((to_email, subject, body, html_body))

    monkeypatch.setattr("app.utils.emailer._send_smtp", fail_smtp)
    monkeypatch.setattr("app.utils.emailer._send_resend", fake_resend)

    with app.app_context():
        assert send_email("user@example.com", "OTP", "123456") is True

    assert delivered == [("user@example.com", "OTP", "123456", None)]


def test_email_file_fallback_writes_outbox_file(tmp_path):
    app = create_app("testing")
    app.config.update(
        EMAIL_BACKEND="auto",
        MAIL_SUPPRESS_SEND=False,
        EMAIL_DELIVERY_ORDER="file",
        EMAIL_FILE_FALLBACK=True,
        EMAIL_OUTBOX_FOLDER=str(tmp_path),
    )

    with app.app_context():
        assert send_email("user@example.com", "OTP", "123456") is True

    outbox_files = list(tmp_path.glob("*.eml"))
    assert len(outbox_files) == 1
    assert "123456" in outbox_files[0].read_text(encoding="utf-8")
