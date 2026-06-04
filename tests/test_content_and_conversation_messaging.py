from app import create_app, db
from app.models import Blog, Category, Conversation, ConversationMember, DeletedContent, Message, User


def create_user(username, email, password="password123"):
    user = User(username=username, email=email, is_verified=True)
    user.set_password(password)
    db.session.add(user)
    return user


def login(client, email, password="password123"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def seed_blog_fixture():
    owner = create_user("owner", "owner@example.com")
    other = create_user("other", "other@example.com")
    category = Category(name="Engineering", slug="engineering")
    db.session.add(category)
    db.session.flush()
    published = Blog(
        title="Published Post",
        slug="published-post",
        content="Hello world from a published post",
        excerpt="Hello",
        status="published",
        user_id=owner.id,
        category_id=category.id,
    )
    draft = Blog(
        title="Draft Post",
        slug="draft-post",
        content="Draft body",
        excerpt="Draft",
        status="draft",
        user_id=owner.id,
        category_id=category.id,
    )
    db.session.add_all([published, draft])
    db.session.commit()
    return owner, other, category, published, draft


def test_my_content_page_and_blog_owner_workflow():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        owner, other, category, published, draft = seed_blog_fixture()
        owner_email = owner.email
        other_email = other.email
        category_id = category.id
        published_id = published.id
        original_slug = published.slug

    with app.test_client() as client:
        assert client.get("/dashboard/content", follow_redirects=False).status_code == 302
        assert client.get(f"/blog/{original_slug}").status_code == 200

        login(client, other_email)
        assert client.get(f"/blog/{published_id}/edit").status_code == 403
        assert client.post(f"/blog/{published_id}/delete", data={"password": "password123"}).status_code == 403

        client.get("/logout")
        login(client, owner_email)
        page = client.get("/dashboard/content")
        assert page.status_code == 200
        assert b"Published Post" in page.data
        assert b"Draft Post" in page.data

        response = client.post(
            f"/blog/{published_id}/edit",
            data={
                "title": "Updated Published Post",
                "content": "Updated content with enough words",
                "excerpt": "Updated excerpt",
                "category_id": category_id,
                "status": "published",
                "tags": "flask, messaging",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        response = client.post(f"/blog/{published_id}/delete", data={"password": "wrong"}, follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Blog, published_id) is not None
            assert DeletedContent.query.filter_by(content_type="blog").count() == 0

        response = client.post(f"/blog/{published_id}/delete", data={"password": "password123"}, follow_redirects=False)
        assert response.status_code == 302

        with app.app_context():
            assert db.session.get(Blog, published_id) is None
            archive = DeletedContent.query.filter_by(content_type="blog", content_id=published_id).first()
            assert archive is not None
            assert archive.can_recover()
            assert archive.content_data["slug"] == original_slug
            archive_id = archive.id

        deleted_page = client.get("/dashboard/content?tab=deleted")
        assert deleted_page.status_code == 200
        assert b"Updated Published Post" in deleted_page.data

        response = client.post(f"/dashboard/content/deleted/{archive_id}/restore", follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            restored = Blog.query.filter_by(slug=original_slug).first()
            assert restored is not None
            assert restored.title == "Updated Published Post"


def test_direct_and_group_conversation_messaging_flow():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        alice = create_user("alice", "alice@example.com")
        bob = create_user("bob", "bob@example.com")
        carol = create_user("carol", "carol@example.com")
        outsider = create_user("outsider", "outsider@example.com")
        db.session.commit()
        alice_email = alice.email
        bob_email = bob.email
        carol_email = carol.email
        outsider_email = outsider.email
        bob_id = bob.id

    with app.test_client() as client:
        login(client, alice_email)
        response = client.post(
            "/messages/send",
            data={"recipient_id": bob_id, "content": "direct hello", "client_id": "direct-client-1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        direct_payload = response.get_json()
        assert direct_payload["status"] == "sent"

        response = client.post(
            "/messages/send",
            data={"recipient_id": bob_id, "content": "duplicated direct hello", "client_id": "direct-client-1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        assert response.get_json()["deduplicated"] is True

        with app.app_context():
            direct = Conversation.query.filter_by(type="direct").first()
            assert direct is not None
            assert ConversationMember.query.filter_by(conversation_id=direct.id).count() == 2
            assert Message.query.filter_by(conversation_id=direct.id, client_id="direct-client-1").count() == 1

        response = client.post(
            "/messages/groups",
            data={"title": "Robot Lab", "members": "bob\ncarol"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            group = Conversation.query.filter_by(type="group", title="Robot Lab").first()
            assert group is not None
            assert ConversationMember.query.filter_by(conversation_id=group.id, is_active=True).count() == 3
            public_id = group.public_id

        page = client.get(f"/messages/c/{public_id}")
        assert page.status_code == 200
        assert b"Robot Lab" in page.data

        response = client.post(
            f"/messages/c/{public_id}/send",
            data={"content": "group hello"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        assert response.get_json()["message"]["content"] == "group hello"

        client.get("/logout")
        login(client, outsider_email)
        assert client.get(f"/messages/c/{public_id}/messages").status_code == 404

        client.get("/logout")
        login(client, bob_email)
        response = client.get(f"/messages/c/{public_id}/messages?after_id=0")
        assert response.status_code == 200
        assert response.get_json()["messages"][0]["content"] == "group hello"
        assert client.post(f"/messages/c/{public_id}/read").status_code == 200

        client.get("/logout")
        login(client, alice_email)
        with app.app_context():
            carol_id = User.query.filter_by(username="carol").first().id
        assert client.post(f"/messages/c/{public_id}/members/{carol_id}/remove", follow_redirects=False).status_code == 302

        client.get("/logout")
        login(client, carol_email)
        assert client.get(f"/messages/c/{public_id}/messages").status_code == 404

        with app.app_context():
            assert Message.query.filter_by(content="group hello").first() is not None


def test_legacy_api_jwt_uses_issuer_audience_and_rate_limited_login():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        create_user("apiuser", "api@example.com")
        db.session.commit()

    with app.test_client() as client:
        response = client.post("/api/login", json={"email": "api@example.com", "password": "password123"})
        assert response.status_code == 200
        token = response.get_json()["token"]

        response = client.get("/api/user", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.get_json()["username"] == "apiuser"

        assert client.get("/api/user", headers={"Authorization": "Bearer invalid"}).status_code == 401
