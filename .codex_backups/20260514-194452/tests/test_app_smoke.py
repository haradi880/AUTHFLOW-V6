from app import create_app, db
from app.models import (
    Blog,
    Bookmark,
    Category,
    DevLog,
    DevLogBookmark,
    DevLogComment,
    DevLogLike,
    DevLogRepost,
    Project,
    ProjectStar,
    Report,
    Tag,
    User,
    XPTransaction,
)
from app.services.gamification import award_xp, level_from_xp, xp_progress


def seed():
    user = User(username="demo", email="demo@example.com", is_verified=True)
    user.set_password("password123")
    category = Category(name="Web Development", slug="web-dev")
    db.session.add_all([user, category])
    db.session.flush()
    db.session.add_all(
        [
            Blog(
                title="Hello",
                slug="hello",
                content="Hello **world**",
                excerpt="Hello",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
            Project(
                title="Project",
                slug="project",
                description="A useful project",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
        ]
    )
    db.session.commit()


def test_public_pages_render():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()

    with app.test_client() as client:
        for path in ["/blogs", "/blog/hello", "/projects", "/project/project", "/demo", "/login", "/register"]:
            response = client.get(path)
            assert response.status_code == 200


def test_cache_headers_for_dynamic_and_static_routes():
    app = create_app("testing")

    with app.test_client() as client:
        login_response = client.get("/login")
        assert login_response.status_code == 200
        assert "no-store" in login_response.headers["Cache-Control"]

        static_response = client.get("/static/css/style.css")
        assert static_response.status_code == 200
        assert "public" in static_response.headers["Cache-Control"]


def test_remember_login_sets_persistent_cookie():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()

    with app.test_client() as client:
        response = client.post(
            "/login",
            data={"email": "demo@example.com", "password": "password123", "remember": "on"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        set_cookie_headers = response.headers.getlist("Set-Cookie")
        assert any("remember_token=" in cookie for cookie in set_cookie_headers)


def test_bookmarks_page_renders_for_logged_in_user():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        user = User.query.filter_by(username="demo").first()
        blog = Blog.query.filter_by(slug="hello").first()
        db.session.add(Bookmark(user_id=user.id, blog_id=blog.id))
        db.session.commit()

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.get("/bookmarks")
        assert response.status_code == 200
        assert b"Bookmarks" in response.data


def test_profile_completion_and_featured_fields_update():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        blog = Blog.query.filter_by(slug="hello").first()
        project = Project.query.filter_by(slug="project").first()
        blog_id = blog.id
        project_id = project.id

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post(
            "/profile/edit",
            data={
                "full_name": "Demo Developer",
                "headline": "Full-stack developer building useful tools",
                "bio": "I build useful software products and write about the lessons learned along the way.",
                "location": "Remote",
                "website": "https://example.com",
                "resume_url": "https://example.com/resume.pdf",
                "skills": "python,flask,sql",
                "twitter": "",
                "linkedin": "https://linkedin.com/in/demo",
                "github": "https://github.com/demo",
                "featured_blog_id": str(blog_id),
                "featured_project_id": str(project_id),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    with app.app_context():
        user = User.query.filter_by(username="demo").first()
        assert user.headline == "Full-stack developer building useful tools"
        assert user.featured_blog_id == blog_id
        assert user.featured_project_id == project_id
        assert user.profile_completion() > 50


def test_public_api_and_tag_suggestions():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        tag = Tag(name="Flask", slug="flask")
        blog = Blog.query.filter_by(slug="hello").first()
        project = Project.query.filter_by(slug="project").first()
        blog.tags.append(tag)
        project.tags.append(tag)
        db.session.commit()

    with app.test_client() as client:
        profiles = client.get("/api/profiles")
        assert profiles.status_code == 200
        assert profiles.get_json()[0]["username"] == "demo"

        blogs = client.get("/api/blogs")
        assert blogs.status_code == 200
        assert blogs.get_json()[0]["slug"] == "hello"

        projects = client.get("/api/projects")
        assert projects.status_code == 200
        assert projects.get_json()[0]["slug"] == "project"

        suggestions = client.get("/tags/suggest?q=fla")
        assert suggestions.status_code == 200
        assert suggestions.get_json()[0]["name"] == "Flask"


def test_devlogs_feed_create_and_ajax_interactions():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        owner = User.query.filter_by(username="demo").first()
        fan = User(username="fan", email="fan@example.com", is_verified=True)
        fan.set_password("password123")
        db.session.add(fan)
        db.session.flush()
        devlog = DevLog(
            content="Day 2 shipped persistent DevLogs #flask",
            progress=55,
            milestone="DevLogs are live",
            user_id=owner.id,
        )
        db.session.add(devlog)
        db.session.commit()
        devlog_id = devlog.id

    with app.test_client() as client:
        assert client.get("/devlogs").status_code == 200
        assert client.get("/devfeed").status_code == 200
        assert client.get("/faq").status_code == 200

        client.post("/login", data={"email": "fan@example.com", "password": "password123"})

        response = client.post(f"/devlogs/{devlog_id}/like", headers={"X-Requested-With": "XMLHttpRequest"})
        assert response.status_code == 200
        assert response.get_json()["status"] == "liked"

        response = client.post(f"/devlogs/{devlog_id}/bookmark", headers={"X-Requested-With": "XMLHttpRequest"})
        assert response.status_code == 200
        assert response.get_json()["status"] == "bookmarked"

        response = client.post(f"/devlogs/{devlog_id}/repost", headers={"X-Requested-With": "XMLHttpRequest"})
        assert response.status_code == 200
        assert response.get_json()["status"] == "reposted"

        response = client.post(
            f"/devlogs/{devlog_id}/comments",
            data={"content": "This is a strong launch log."},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        assert response.get_json()["count"] == 1

        response = client.post(
            "/devlogs",
            data={"content": "Day 1 building the feed engine #buildinpublic", "progress": "25", "milestone": "Started"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )
        assert response.status_code == 201
        assert "devlog-card" in response.get_json()["html"]

    with app.app_context():
        devlog = DevLog.query.get(devlog_id)
        fan = User.query.filter_by(username="fan").first()
        assert devlog.likes_count == 1
        assert devlog.bookmarks_count == 1
        assert devlog.reposts_count == 1
        assert devlog.comments_count == 1
        assert DevLogLike.query.filter_by(user_id=fan.id, devlog_id=devlog_id).count() == 1
        assert DevLogBookmark.query.filter_by(user_id=fan.id, devlog_id=devlog_id).count() == 1
        assert DevLogRepost.query.filter_by(user_id=fan.id, devlog_id=devlog_id).count() == 1
        assert DevLogComment.query.filter_by(user_id=fan.id, devlog_id=devlog_id).count() == 1
        assert DevLog.query.filter_by(user_id=fan.id).count() == 1


def test_resend_otp_endpoint_for_pending_signup(monkeypatch):
    app = create_app("testing")
    sent = []

    def fake_send_otp(email, code):
        sent.append((email, code))

    monkeypatch.setattr("app.utils.emailer.send_otp_email", fake_send_otp)

    with app.app_context():
        db.create_all()
        user = User(username="pending", email="pending@example.com", is_verified=False)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["verify_email"] = "pending@example.com"
        response = client.post("/resend-otp", json={"purpose": "email_verification"}, headers={"Accept": "application/json"})
        assert response.status_code == 200
        assert response.get_json()["success"] is True
        assert sent and sent[0][0] == "pending@example.com"


def test_admin_can_moderate_reports_and_suspend_user():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        admin = User(username="admin", email="admin@example.com", is_admin=True, is_verified=True)
        admin.set_password("password123")
        demo = User.query.filter_by(username="demo").first()
        db.session.add(admin)
        db.session.add(Report(reporter_id=admin.id, reported_user_id=demo.id, reason="spam"))
        db.session.commit()
        demo_id = demo.id
        report_id = Report.query.first().id

    with app.test_client() as client:
        client.post("/login", data={"email": "admin@example.com", "password": "password123"})
        response = client.post(f"/admin/users/{demo_id}/toggle-active", follow_redirects=False)
        assert response.status_code == 302
        response = client.post(f"/admin/reports/{report_id}/status", data={"status": "resolved"}, follow_redirects=False)
        assert response.status_code == 302

    with app.app_context():
        assert User.query.get(demo_id).active is False
        assert Report.query.get(report_id).status == "resolved"


def test_xp_awards_are_progressive_and_abuse_limited():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        user = User.query.filter_by(username="demo").first()
        assert level_from_xp(0) == 1
        assert xp_progress(100)["level"] >= 2

        first = award_xp(user, "daily_login")
        second = award_xp(user, "daily_login")
        assert first is not None
        assert second is None
        assert XPTransaction.query.filter_by(user_id=user.id, action="daily_login").count() == 1
        assert user.xp_total == 10


def test_publishing_and_project_stars_award_xp():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        owner = User.query.filter_by(username="demo").first()
        fan = User(username="fan", email="fan@example.com", is_verified=True)
        fan.set_password("password123")
        db.session.add(fan)
        db.session.commit()
        owner_start_xp = owner.xp_total
        project_id = Project.query.filter_by(slug="project").first().id

    with app.test_client() as client:
        client.post("/login", data={"email": "fan@example.com", "password": "password123"})
        response = client.post(f"/project/{project_id}/star")
        assert response.status_code == 200
        assert response.get_json()["status"] == "starred"

    with app.app_context():
        owner = User.query.filter_by(username="demo").first()
        assert ProjectStar.query.filter_by(project_id=project_id).count() == 1
        assert owner.xp_total == owner_start_xp + 10
