from app import create_app, db
from app.models import Blog, Category, Project, User
from app.services.load import load_summary, run_load_targets


def seed_public_content():
    user = User(username="load", email="load@example.com", is_verified=True)
    user.set_password("password123")
    category = Category(name="Load", slug="load")
    db.session.add_all([user, category])
    db.session.flush()
    db.session.add_all(
        [
            Blog(
                title="Load Blog",
                slug="load-blog",
                content="Load content",
                excerpt="Load",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
            Project(
                title="Load Project",
                slug="load-project",
                description="Load project",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
        ]
    )
    db.session.commit()


def test_internal_load_targets_pass_with_seeded_app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_public_content()

    stable_targets = [
        {"path": "/healthz", "expected": {200}},
        {"path": "/login", "expected": {200}},
        {"path": "/messages", "expected": {302}},
    ]
    results = run_load_targets(app=app, requests_per_target=2, concurrency=2, max_p95_ms=10_000, targets=stable_targets)
    summary = load_summary(results)
    assert summary["failures"] == 0
    assert summary["total_requests"] == 6
    assert summary["completed_requests"] == 6
    by_path = {result.path: result for result in results}
    assert by_path["/messages"].statuses == {"302": 2}


def test_load_check_cli_outputs_json():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_public_content()

    result = app.test_cli_runner().invoke(
        args=[
            "load-check",
            "--json",
            "--requests-per-target",
            "2",
            "--concurrency",
            "2",
            "--max-p95-ms",
            "10000",
            "--target",
            "/healthz",
            "--target",
            "/login",
            "--target",
            "/messages",
        ]
    )
    assert result.exit_code == 0
    assert '"failures": 0' in result.output
    assert '"total_requests": 6' in result.output
    assert '"/healthz"' in result.output
