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
    RoboticsProject,
    Tag,
    User,
    XPTransaction,
    Company,
    Job,
    JobApplication,
    LoginEvent,
    LoginSession,
    Notification,
    DevLogComment,
    Team,
    TeamInvitation,
    TeamMember,
    DonationIntent,
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


def test_logout_clears_remember_cookie():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()

    with app.test_client() as client:
        client.post(
            "/login",
            data={"email": "demo@example.com", "password": "password123", "remember": "on"},
            follow_redirects=False,
        )
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        set_cookie_headers = response.headers.getlist("Set-Cookie")
        assert any("remember_token=;" in cookie and ("Expires=Thu, 01 Jan 1970" in cookie or "Max-Age=0" in cookie) for cookie in set_cookie_headers)


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


def test_robotics_project_upload_and_delete():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        assert client.get("/robotics/upload").status_code == 200
        response = client.post(
            "/robotics/upload",
            data={
                "title": "ESP32 Line Follower",
                "description": "A compact robotics build with sensors, motor driver, and tuning notes.",
                "project_type": "esp32",
                "difficulty": "intermediate",
                "status": "published",
                "tags": "esp32, robotics",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    with app.app_context():
        project = RoboticsProject.query.filter_by(slug="esp32-line-follower").first()
        assert project is not None
        project_id = project.id

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post(f"/robotics/{project_id}/delete", follow_redirects=False)
        assert response.status_code == 302

    with app.app_context():
        assert RoboticsProject.query.get(project_id) is None


def test_hiring_job_post_profile_fields_and_delete():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post(
            "/profile/edit",
            data={
                "full_name": "Demo Developer",
                "headline": "Robotics engineer",
                "bio": "I build practical robotics and backend tools for teams.",
                "location": "Remote",
                "website": "https://example.com",
                "resume_url": "https://example.com/resume.pdf",
                "skills": "python,ros,embedded",
                "twitter": "",
                "linkedin": "https://linkedin.com/in/demo",
                "github": "https://github.com/demo",
                "open_to_work": "on",
                "availability_status": "available-now",
                "job_title": "Robotics Engineer",
                "years_experience": "4",
                "preferred_work_type": "remote",
                "is_recruiter": "on",
                "robotics_specialties": "ROS, ESP32",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        response = client.post(
            "/hiring/post",
            data={
                "title": "Robotics Platform Engineer",
                "description": "Build robotics platform features, device integrations, and developer tooling.",
                "category": "robotics",
                "job_type": "contract",
                "work_mode": "remote",
                "experience_level": "mid",
                "location": "Remote",
                "skills_required": "python, ros",
                "company_name": "Example Robotics",
                "company_website": "https://example.com",
                "status": "active",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    with app.app_context():
        user = User.query.filter_by(username="demo").first()
        assert user.open_to_work is True
        assert user.is_recruiter is True
        job = Job.query.filter_by(slug="robotics-platform-engineer").first()
        assert job is not None
        assert Company.query.filter_by(name="Example Robotics").first() is not None
        job_id = job.id

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post(f"/hiring/{job_id}/delete", follow_redirects=False)
        assert response.status_code == 302

    with app.app_context():
        assert Job.query.get(job_id) is None


def test_job_application_notifications_and_status_tracking():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        recruiter = User(username="recruiter", email="recruiter@example.com", is_verified=True)
        recruiter.set_password("password123")
        company = Company(name="Acme Robotics", slug="acme-robotics", created_by=recruiter)
        db.session.add_all([recruiter, company])
        db.session.flush()
        job = Job(
            title="Robotics Engineer",
            slug="robotics-engineer",
            description="Build production robots and developer tools.",
            job_type="full-time",
            work_mode="remote",
            category="robotics",
            company_id=company.id,
            posted_by_id=recruiter.id,
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post(f"/hiring/apply/{job_id}", data={"cover_note": "I build robots."}, follow_redirects=False)
        assert response.status_code == 302

    with app.app_context():
        application = JobApplication.query.filter_by(job_id=job_id).first()
        applicant = User.query.filter_by(username="demo").first()
        recruiter = User.query.filter_by(username="recruiter").first()
        assert application.status == "applied"
        assert Notification.query.filter_by(user_id=applicant.id, action="job_application_submitted").count() == 1
        assert Notification.query.filter_by(user_id=recruiter.id, action="job_application_received").count() == 1

    with app.test_client() as client:
        client.post("/login", data={"email": "recruiter@example.com", "password": "password123"})
        response = client.post(
            f"/hiring/applications/{application.id}/status",
            data={"status": "shortlisted", "recruiter_response": "Strong portfolio."},
            follow_redirects=False,
        )
        assert response.status_code == 302

    with app.app_context():
        application = db.session.get(JobApplication, application.id)
        applicant = User.query.filter_by(username="demo").first()
        assert application.status == "shortlisted"
        assert application.recruiter_response == "Strong portfolio."
        assert Notification.query.filter_by(user_id=applicant.id, action="job_application_status").count() == 1


def test_team_invitation_acceptance_creates_membership_and_notification():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        invitee = User(username="builder", email="builder@example.com", is_verified=True)
        invitee.set_password("password123")
        db.session.add(invitee)
        db.session.commit()

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post("/collaboration/teams/new", data={"name": "Robot Lab", "description": "Shared builds"}, follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            team = Team.query.filter_by(slug="robot-lab").first()
            assert team is not None
            assert TeamMember.query.filter_by(team_id=team.id, role="owner").count() == 1
        response = client.post(f"/collaboration/teams/{team.id}/invite", data={"user": "builder", "role": "member"}, follow_redirects=False)
        assert response.status_code == 302

    with app.app_context():
        invitee = User.query.filter_by(username="builder").first()
        invitation = TeamInvitation.query.filter_by(invitee_id=invitee.id, status="pending").first()
        assert invitation is not None
        assert Notification.query.filter_by(user_id=invitee.id, action="team_invitation").count() == 1

    with app.test_client() as client:
        client.post("/login", data={"email": "builder@example.com", "password": "password123"})
        response = client.post(f"/collaboration/invitations/{invitation.id}/accept", follow_redirects=False)
        assert response.status_code == 302

    with app.app_context():
        invitation = db.session.get(TeamInvitation, invitation.id)
        invitee = User.query.filter_by(username="builder").first()
        assert invitation.status == "accepted"
        assert TeamMember.query.filter_by(team_id=invitation.team_id, user_id=invitee.id).count() == 1


def test_login_creates_device_history_and_settings_renders():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()

    with app.test_client() as client:
        response = client.post(
            "/login",
            data={"email": "demo@example.com", "password": "password123"},
            headers={"User-Agent": "Mozilla/5.0 Chrome Windows"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        settings_response = client.get("/settings")
        assert settings_response.status_code == 200
        assert b"Login Devices" in settings_response.data

    with app.app_context():
        user = User.query.filter_by(username="demo").first()
        assert LoginSession.query.filter_by(user_id=user.id).count() == 1
        assert LoginEvent.query.filter_by(user_id=user.id, success=True).count() == 1


def test_support_upi_qr_generation_logs_donation_intent():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()

    with app.test_client() as client:
        response = client.post("/api/generate-qr", json={"amount": 99})
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "upi://pay?pa=llaka2937-1@okicici&pn=ADITYA&am=99.00&cu=INR" == data["upi_link"]
        assert data["qr_code"]

    with app.app_context():
        intent = DonationIntent.query.first()
        assert intent is not None
        assert str(intent.amount) == "99.00"


def test_devlog_comment_and_devlog_delete():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed()
        user = User.query.filter_by(username="demo").first()
        devlog = DevLog(content="Delete flow test", progress=10, user_id=user.id)
        db.session.add(devlog)
        db.session.commit()
        devlog_id = devlog.id

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post(
            f"/devlogs/{devlog_id}/comments",
            data={"content": "Owner can remove this."},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200

    with app.app_context():
        comment = DevLogComment.query.filter_by(devlog_id=devlog_id).first()
        assert comment is not None
        comment_id = comment.id

    with app.test_client() as client:
        client.post("/login", data={"email": "demo@example.com", "password": "password123"})
        response = client.post(
            f"/devlogs/comments/{comment_id}/delete",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        assert response.get_json()["status"] == "deleted"
        response = client.post(
            f"/devlogs/{devlog_id}/delete",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        assert response.get_json()["status"] == "deleted"

    with app.app_context():
        assert DevLog.query.get(devlog_id) is None
