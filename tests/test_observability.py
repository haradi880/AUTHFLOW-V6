from sqlalchemy import event

from app import create_app, db


def test_request_id_header_is_generated_and_echoed():
    app = create_app("testing")

    with app.test_client() as client:
        generated = client.get("/healthz")
        assert generated.status_code == 200
        assert generated.headers.get("X-Request-ID")

        custom = client.get("/healthz", headers={"X-Request-ID": "req-test-12345"})
        assert custom.headers["X-Request-ID"] == "req-test-12345"

        unsafe = client.get("/healthz", headers={"X-Request-ID": "../../bad"})
        assert unsafe.headers["X-Request-ID"] != "../../bad"


def test_readyz_checks_database():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

    with app.test_client() as client:
        response = client.get("/readyz")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["checks"]["database"]["ok"] is True


def test_readyz_reuses_recent_successful_database_check():
    app = create_app("testing")
    app.config["READINESS_CACHE_SECONDS"] = 60
    with app.app_context():
        db.create_all()

    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if "select 1" in statement.lower():
            statements.append(statement)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
        try:
            with app.test_client() as client:
                first = client.get("/readyz")
                second = client.get("/readyz")
        finally:
            event.remove(db.engine, "before_cursor_execute", before_cursor_execute)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()["checks"]["database"]["cached"] is False
    assert second.get_json()["checks"]["database"]["cached"] is True
    assert len(statements) == 1


def test_metrics_endpoint_outputs_prometheus_text_and_supports_token():
    app = create_app("testing")

    with app.test_client() as client:
        client.get("/healthz")
        response = client.get("/metrics")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "haradibots_requests_total" in body
        assert "haradibots_process_uptime_seconds" in body

        app.config["METRICS_TOKEN"] = "secret-token"
        assert client.get("/metrics").status_code == 403
        assert client.get("/metrics", headers={"Authorization": "Bearer secret-token"}).status_code == 200
