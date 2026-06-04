from sqlalchemy import event

from app import create_app, db
from app.models import Blog, Category, Project, Tag, User


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.sets = 0

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.sets += 1
        self.store[key] = bytes(value)


def seed_feed_items(count=6):
    user = User(username="perf", email="perf@example.com", is_verified=True)
    user.set_password("password123")
    category = Category(name="Performance", slug="performance")
    tag = Tag(name="Flask", slug="flask")
    db.session.add_all([user, category, tag])
    db.session.flush()
    for index in range(count):
        blog = Blog(
            title=f"Perf Blog {index}",
            slug=f"perf-blog-{index}",
            content="Performance content",
            excerpt="Performance",
            status="published",
            user_id=user.id,
            category_id=category.id,
        )
        blog.tags.append(tag)
        project = Project(
            title=f"Perf Project {index}",
            slug=f"perf-project-{index}",
            description="Performance project",
            status="published",
            user_id=user.id,
            category_id=category.id,
        )
        project.tags.append(tag)
        db.session.add_all([blog, project])
    db.session.commit()


def count_queries(app, path):
    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = app.test_client().get(path)
        finally:
            event.remove(db.engine, "before_cursor_execute", before_cursor_execute)
    return response, statements


def test_feed_pages_do_not_scale_with_per_item_lazy_loads():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_feed_items(count=8)

    blogs_response, blog_queries = count_queries(app, "/blogs")
    projects_response, project_queries = count_queries(app, "/projects")

    assert blogs_response.status_code == 200
    assert projects_response.status_code == 200
    assert len(blog_queries) <= 5
    assert len(project_queries) <= 4
    assert not any(" count(" in statement.lower() for statement in blog_queries + project_queries)
    assert not any("blogs.content" in statement.lower() for statement in blog_queries)


def test_public_feeds_use_redis_cache_for_anonymous_requests():
    app = create_app("testing")
    app.config.update(PUBLIC_PAGE_CACHE_ENABLED=True, PUBLIC_PAGE_CACHE_SECONDS=60, REDIS_URL="redis://cache")
    fake_redis = FakeRedis()
    app.extensions["redis_cache_client"] = fake_redis
    with app.app_context():
        db.create_all()
        seed_feed_items(count=3)

    with app.test_client() as client:
        first = client.get("/blogs")
        second = client.get("/blogs")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["X-HaradiBots-Cache"] == "MISS"
    assert second.headers["X-HaradiBots-Cache"] == "HIT"
    assert first.get_data() == second.get_data()
    assert fake_redis.sets == 1


def test_public_feed_cache_is_bypassed_when_request_has_cookie():
    app = create_app("testing")
    app.config.update(PUBLIC_PAGE_CACHE_ENABLED=True, PUBLIC_PAGE_CACHE_SECONDS=60, REDIS_URL="redis://cache")
    fake_redis = FakeRedis()
    app.extensions["redis_cache_client"] = fake_redis
    with app.app_context():
        db.create_all()
        seed_feed_items(count=3)

    with app.test_client() as client:
        client.set_cookie("session", "fake")
        response = client.get("/projects")

    assert response.status_code == 200
    assert "X-HaradiBots-Cache" not in response.headers
    assert fake_redis.sets == 0
