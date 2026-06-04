import pytest

from app import create_app, db
from app.models import User
from app.realtime import socketio


def create_user(username, email):
    user = User(username=username, email=email, is_verified=True)
    user.set_password("password123")
    db.session.add(user)
    return user


@pytest.mark.skipif(socketio is None, reason="Flask-SocketIO is not installed")
def test_notification_room_uses_authenticated_user_not_client_payload():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        user = create_user("socket-user", "socket-user@example.com")
        other = create_user("socket-other", "socket-other@example.com")
        db.session.commit()
        user_id = user.id
        other_id = other.id

    flask_client = app.test_client()
    flask_client.post("/login", data={"email": "socket-user@example.com", "password": "password123"})
    client = socketio.test_client(app, flask_test_client=flask_client)

    payload = client.emit("join_notifications", {"user_id": other_id}, callback=True)

    assert payload == {"room": f"user:{user_id}"}
    assert payload != {"room": f"user:{other_id}"}
