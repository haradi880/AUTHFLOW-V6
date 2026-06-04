from app import create_app, db
from app.models import Blog, Category, DeletedContent, Project, User
from app.utils.soft_delete import restore_deleted_content, soft_delete


def seed_author_and_category():
    user = User(username="delete-demo", email="delete-demo@example.com", is_verified=True)
    user.set_password("password123")
    category = Category(name="Soft Delete", slug="soft-delete")
    db.session.add_all([user, category])
    db.session.commit()
    return user, category


def test_soft_delete_archives_blog_and_restore_recreates_row():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        user, category = seed_author_and_category()
        blog = Blog(
            title="Recoverable Blog",
            slug="recoverable-blog",
            content="A post worth recovering.",
            excerpt="A post",
            status="published",
            user_id=user.id,
            category_id=category.id,
        )
        db.session.add(blog)
        db.session.commit()
        blog_id = blog.id

        assert soft_delete(blog, "blog", user_id=user.id, reason="test") is True
        archive = DeletedContent.query.filter_by(content_type="blog", content_id=blog_id).one()
        assert db.session.get(Blog, blog_id) is None
        assert archive.can_recover()

        restored = restore_deleted_content(archive.id, user_id=user.id)
        assert restored is not None
        assert restored.title == "Recoverable Blog"
        assert db.session.get(DeletedContent, archive.id).recovered is True


def test_soft_delete_archives_project_and_restore_recreates_row():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        user, category = seed_author_and_category()
        project = Project(
            title="Recoverable Project",
            slug="recoverable-project",
            description="A project worth recovering.",
            status="published",
            user_id=user.id,
            category_id=category.id,
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

        assert soft_delete(project, "project", user_id=user.id, reason="test") is True
        archive = DeletedContent.query.filter_by(content_type="project", content_id=project_id).one()
        assert db.session.get(Project, project_id) is None

        restored = restore_deleted_content(archive.id, user_id=user.id)
        assert restored is not None
        assert restored.title == "Recoverable Project"
        assert db.session.get(DeletedContent, archive.id).recovered is True
