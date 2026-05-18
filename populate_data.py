import os

from app import create_app
from app.extensions import db
from app.models import Blog, Category, DevLog, Message, Notification, Project, Tag, User
from app.services.content import sync_tags
from app.services.gamification import award_xp


CATEGORIES = [
    ("AI & Machine Learning", "ai-ml"),
    ("Web Development", "web-dev"),
    ("Mobile Development", "mobile-dev"),
    ("DevOps & Cloud", "devops"),
    ("Robotics", "robotics"),
    ("Data Science", "data-science"),
    ("Cybersecurity", "cybersecurity"),
    ("IoT", "iot"),
]

TAGS = [
    "python",
    "javascript",
    "react",
    "flask",
    "docker",
    "kubernetes",
    "machine-learning",
    "deep-learning",
    "nlp",
    "computer-vision",
]


def get_or_create(model, defaults=None, **lookup):
    item = model.query.filter_by(**lookup).first()
    if item:
        return item, False
    item = model(**lookup, **(defaults or {}))
    db.session.add(item)
    return item, True


def populate(app):
    """Idempotently populate local/demo data."""
    with app.app_context():
        db.create_all()

        for name, slug in CATEGORIES:
            get_or_create(Category, name=name, slug=slug)

        for tag_name in TAGS:
            get_or_create(Tag, name=tag_name, slug=tag_name)

        admin, admin_created = get_or_create(
            User,
            username="admin",
            defaults={
                "email": os.getenv("ADMIN_EMAIL", "admin@authflow.local"),
                "full_name": "AuthFlow Admin",
                "headline": "Platform administrator",
                "bio": "Maintains the AuthFlow community and moderation workflows.",
                "is_admin": True,
                "is_verified": True,
            },
        )
        if admin_created:
            admin.set_password(os.getenv("ADMIN_PASSWORD", "change-me-admin"))

        demo, demo_created = get_or_create(
            User,
            username="demo",
            defaults={
                "email": "demo@authflow.local",
                "full_name": "Demo Developer",
                "headline": "Full-stack developer building Flask and AI tools",
                "bio": "I build useful software products and share practical notes from the work.",
                "location": "Remote",
                "website": "https://demo.dev",
                "skills": "python,flask,javascript,ai,docker",
                "github": "https://github.com/demo",
                "linkedin": "https://linkedin.com/in/demo",
                "is_verified": True,
            },
        )
        if demo_created:
            demo.set_password(os.getenv("DEMO_PASSWORD", "demo12345!"))

        db.session.flush()

        web = Category.query.filter_by(slug="web-dev").first()
        if not Blog.query.filter_by(slug="welcome-to-authflow").first():
            blog = Blog(
                title="Welcome to AuthFlow",
                slug="welcome-to-authflow",
                content="AuthFlow is a developer community for publishing, projects, and build-in-public work.",
                excerpt="A quick tour of the AuthFlow developer platform.",
                status="published",
                reading_time=1,
                user_id=demo.id,
                category_id=web.id if web else None,
            )
            db.session.add(blog)
            sync_tags(blog, "flask, python, community")
            db.session.flush()
            award_xp(demo, "publish_blog", source=blog, commit=False)

        if not Project.query.filter_by(slug="authflow-platform").first():
            project = Project(
                title="AuthFlow Platform",
                slug="authflow-platform",
                description="A Flask developer social platform with profiles, blogs, projects, messages, and gamification.",
                github_url="https://github.com/example/authflow",
                demo_url="https://authflow.local",
                status="published",
                user_id=demo.id,
                category_id=web.id if web else None,
            )
            db.session.add(project)
            sync_tags(project, "flask, python, social")
            db.session.flush()
            award_xp(demo, "publish_project", source=project, commit=False)

        if not DevLog.query.first():
            devlog = DevLog(
                content="Day 1: seeded AuthFlow with profiles, publishing, projects, messages, and the first build-in-public DevLog. #flask #buildinpublic",
                progress=35,
                milestone="Developer ecosystem foundation is online",
                user_id=demo.id,
                is_pinned=True,
            )
            db.session.add(devlog)
            sync_tags(devlog, "flask, buildinpublic, community")
            db.session.flush()
            award_xp(demo, "daily_devlog", commit=False)

        if not Message.query.first():
            db.session.add_all(
                [
                    Message(sender_id=admin.id, recipient_id=demo.id, content="Welcome to AuthFlow. Your demo workspace is ready."),
                    Message(sender_id=demo.id, recipient_id=admin.id, content="Thanks. The platform already feels alive."),
                ]
            )

        if not Notification.query.first():
            db.session.add(
                Notification(
                    user_id=demo.id,
                    action="system",
                    message="Welcome to AuthFlow. Complete your profile to earn XP.",
                    from_user_id=admin.id,
                )
            )

        db.session.commit()
        print("Database checked and demo data is ready.")


if __name__ == "__main__":
    app = create_app()
    populate(app)
    print("\nSample accounts:")
    print(f"  Admin: {os.getenv('ADMIN_EMAIL', 'admin@authflow.local')} / {os.getenv('ADMIN_PASSWORD', 'change-me-admin')}")
    print(f"  User:  demo@authflow.local / {os.getenv('DEMO_PASSWORD', 'demo12345!')}")
