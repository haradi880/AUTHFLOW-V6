from app import create_app, db
from app.models import Blog, Category, Project, User
from app.services.smoke import run_smoke_targets, smoke_summary


def seed_public_content():
    user = User(username="smoke", email="smoke@example.com", is_verified=True)
    user.set_password("password123")
    category = Category(name="Smoke", slug="smoke")
    db.session.add_all([user, category])
    db.session.flush()
    db.session.add_all(
        [
            Blog(
                title="Smoke Blog",
                slug="smoke-blog",
                content="Smoke content",
                excerpt="Smoke",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
            Project(
                title="Smoke Project",
                slug="smoke-project",
                description="Smoke project",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
        ]
    )
    db.session.commit()


def test_internal_smoke_targets_pass_with_seeded_app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_public_content()

    results = run_smoke_targets(app=app, iterations=1, max_p95_ms=10_000)
    assert smoke_summary(results)["failures"] == 0
    by_path = {result.path: result for result in results}
    assert by_path["/blogs"].statuses == [200]
    assert by_path["/messages"].statuses == [302]


def test_smoke_check_cli_outputs_json():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_public_content()

    result = app.test_cli_runner().invoke(args=["smoke-check", "--json", "--max-p95-ms", "10000"])
    assert result.exit_code == 0
    assert '"failures": 0' in result.output
    assert '"/readyz"' in result.output
