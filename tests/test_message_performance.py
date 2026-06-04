from sqlalchemy import event

from app import create_app, db
from app.models import Message, User
from app.services.messaging import create_message, get_or_create_direct_conversation


def create_user(username, email):
    user = User(username=username, email=email, is_verified=True)
    user.set_password("password123")
    db.session.add(user)
    return user


def login(client, email):
    return client.post("/login", data={"email": email, "password": "password123"})


def count_queries(app, client, path):
    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        response = client.get(path)
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    return response, len(statements)


def test_messages_inbox_does_not_lazy_load_per_conversation():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        owner = create_user("inbox-owner", "inbox-owner@example.com")
        for index in range(12):
            other = create_user(f"inbox-user-{index}", f"inbox-user-{index}@example.com")
            db.session.flush()
            conversation = get_or_create_direct_conversation(owner, other)
            create_message(conversation, other, f"hello {index}", client_id=f"seed-{index}")
        db.session.commit()
        owner_email = owner.email

    with app.test_client() as client:
        login(client, owner_email)
        response, query_count = count_queries(app, client, "/messages")

    assert response.status_code == 200
    assert query_count <= 18
