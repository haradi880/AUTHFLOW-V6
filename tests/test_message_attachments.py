from io import BytesIO
from pathlib import Path

from app import create_app, db
from app.models import Message, User
from werkzeug.datastructures import FileStorage


def create_user(username, email):
    user = User(username=username, email=email, is_verified=True)
    user.set_password("password123")
    db.session.add(user)
    return user


def login(client, email):
    return client.post("/login", data={"email": email, "password": "password123"})


def test_message_attachment_is_private_to_conversation_participants(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir(parents=True)

    with app.app_context():
        db.create_all()
        sender = create_user("sender", "sender@example.com")
        recipient = create_user("recipient", "recipient@example.com")
        outsider = create_user("outsider", "outsider@example.com")
        db.session.flush()
        message = Message(
            sender_id=sender.id,
            recipient_id=recipient.id,
            content="see attachment",
            attachment_filename="private-note.txt",
            attachment_original_name="private-note.txt",
            attachment_mime="text/plain",
            attachment_size=11,
        )
        db.session.add(message)
        db.session.commit()
        message_id = message.id
        outsider_email = outsider.email
        sender_email = sender.email

    Path(messages_dir / "private-note.txt").write_text("hello world", encoding="utf-8")

    with app.test_client() as client:
        assert client.get("/uploads/messages/private-note.txt").status_code == 404

        login(client, sender_email)
        response = client.get(f"/messages/attachments/{message_id}")
        assert response.status_code == 200
        assert response.data == b"hello world"

        client.get("/logout")
        login(client, outsider_email)
        assert client.get(f"/messages/attachments/{message_id}").status_code == 404


def test_message_attachment_download_name_is_header_safe(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir(parents=True)

    with app.app_context():
        db.create_all()
        sender = create_user("safe-sender", "safe-sender@example.com")
        recipient = create_user("safe-recipient", "safe-recipient@example.com")
        db.session.flush()
        message = Message(
            sender_id=sender.id,
            recipient_id=recipient.id,
            content="see attachment",
            attachment_filename="safe-note.txt",
            attachment_original_name='bad"\r\nX-Injected: yes.txt',
            attachment_mime="text/plain",
            attachment_size=11,
        )
        db.session.add(message)
        db.session.commit()
        message_id = message.id
        sender_email = sender.email

    Path(messages_dir / "safe-note.txt").write_text("hello world", encoding="utf-8")

    with app.test_client() as client:
        login(client, sender_email)
        response = client.get(f"/messages/attachments/{message_id}")
        assert response.status_code == 200
        assert "X-Injected" not in response.headers
        assert "bad_X-Injected_yes.txt" in response.headers["Content-Disposition"]


def test_legacy_attachment_mime_is_normalized_on_download(tmp_path):
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir(parents=True)

    with app.app_context():
        db.create_all()
        sender = create_user("mime-sender", "mime-sender@example.com")
        recipient = create_user("mime-recipient", "mime-recipient@example.com")
        db.session.flush()
        message = Message(
            sender_id=sender.id,
            recipient_id=recipient.id,
            content="see attachment",
            attachment_filename="spoofed-note.txt",
            attachment_original_name="spoofed-note.txt",
            attachment_mime="text/html",
            attachment_size=12,
        )
        db.session.add(message)
        db.session.commit()
        message_id = message.id
        sender_email = sender.email

    Path(messages_dir / "spoofed-note.txt").write_text("<b>hello</b>", encoding="utf-8")

    with app.test_client() as client:
        login(client, sender_email)
        response = client.get(f"/messages/attachments/{message_id}")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.headers["Content-Disposition"].startswith("inline")


def test_message_attachment_upload_ignores_spoofed_client_mime(tmp_path):
    from app.utils.uploads import save_message_attachment

    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    upload = FileStorage(
        stream=BytesIO(b"<b>plain text, not html</b>"),
        filename="note.txt",
        content_type="text/html",
    )

    with app.app_context():
        data, error = save_message_attachment(upload)

    assert error is None
    assert data["mime"] == "text/plain; charset=utf-8"


def test_invalid_pdf_attachment_is_rejected_even_with_pdf_mime(tmp_path):
    from app.utils.uploads import save_message_attachment

    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    upload = FileStorage(
        stream=BytesIO(b"<html>not a pdf</html>"),
        filename="report.pdf",
        content_type="application/pdf",
    )

    with app.app_context():
        data, error = save_message_attachment(upload)

    assert data is None
    assert error == "The attachment could not be saved."
