from app.services.production_checks import production_check_summary, run_production_checks


def production_config(**overrides):
    config = {
        "APP_ENV": "production",
        "SECRET_KEY": "x" * 48,
        "SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@db:5432/haradibots",
        "RATELIMIT_STORAGE_URI": "redis://redis:6379/0",
        "REDIS_URL": "redis://redis:6379/0",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "service-role-key",
        "UPLOAD_STORAGE_BUCKET": "uploads",
        "PRIVATE_UPLOAD_STORAGE_BUCKET": "private-uploads",
        "BACKUP_STORAGE_BUCKET": "backups",
        "UPLOAD_KEEP_LOCAL": False,
        "MAX_CONTENT_LENGTH": 25 * 1024 * 1024,
        "MAX_UPLOAD_BYTES": 25 * 1024 * 1024,
        "MESSAGE_ATTACHMENT_MAX_BYTES": 25 * 1024 * 1024,
        "EMAIL_BACKEND": "smtp",
        "EMAIL_DELIVERY_ORDER": "smtp",
        "MAIL_SERVER": "smtp.example.com",
        "MAIL_PORT": 587,
        "MAIL_USERNAME": "mailer@example.com",
        "MAIL_PASSWORD": "app-password",
        "MAIL_DEFAULT_SENDER": "mailer@example.com",
        "WTF_CSRF_ENABLED": True,
        "SESSION_COOKIE_SECURE": True,
        "REMEMBER_COOKIE_SECURE": True,
        "PUBLIC_BASE_URL": "https://haradibots.example.com",
        "METRICS_TOKEN": "metrics-token",
        "VIRUS_SCAN_ENABLED": False,
        "VIRUS_SCAN_COMMAND": "",
    }
    config.update(overrides)
    return config


def test_production_checks_pass_for_hardened_config():
    checks = run_production_checks(production_config())
    summary = production_check_summary(checks)
    assert summary == {"total": len(checks), "failures": 0, "warnings": 0}


def test_production_checks_fail_for_common_bad_deploy_config():
    checks = run_production_checks(
        production_config(
            SECRET_KEY="dev-only-change-me",
            SQLALCHEMY_DATABASE_URI="sqlite:///platform.db",
            RATELIMIT_STORAGE_URI="memory://",
            SUPABASE_URL="",
            EMAIL_BACKEND="resend",
            EMAIL_DELIVERY_ORDER="resend,sendgrid",
            MAX_CONTENT_LENGTH=50 * 1024 * 1024,
        )
    )
    statuses = {check.key: check.status for check in checks}
    assert statuses["secret_key"] == "fail"
    assert statuses["database"] == "fail"
    assert statuses["rate_limits"] == "fail"
    assert statuses["supabase"] == "fail"
    assert statuses["email_backend"] == "fail"
    assert statuses["upload_limits"] == "fail"
    assert production_check_summary(checks)["failures"] >= 6
