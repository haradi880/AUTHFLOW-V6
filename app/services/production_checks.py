from dataclasses import dataclass
from urllib.parse import urlparse


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PLACEHOLDER_SECRETS = {
    "",
    "dev-only-change-me",
    "change-me",
    "replace-with-a-long-random-secret",
    "change-me-metrics-token",
}


@dataclass(frozen=True)
class ProductionCheck:
    key: str
    status: str
    message: str
    detail: str = ""

    @property
    def ok(self):
        return self.status == "pass"


def _present(value):
    return bool(str(value or "").strip())


def _is_https_url(value):
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and bool(parsed.netloc)


def _check(condition, key, message, detail="", failure_status="fail"):
    return ProductionCheck(key, "pass" if condition else failure_status, message, detail)


def run_production_checks(config):
    """Return production readiness checks for deployment-critical settings."""
    database_uri = config.get("SQLALCHEMY_DATABASE_URI") or ""
    ratelimit_uri = config.get("RATELIMIT_STORAGE_URI") or ""
    secret_key = config.get("SECRET_KEY") or ""
    email_backend = (config.get("EMAIL_BACKEND") or "").lower()
    delivery_order = [item.strip().lower() for item in (config.get("EMAIL_DELIVERY_ORDER") or "").split(",") if item.strip()]

    checks = [
        _check(
            config.get("APP_ENV") == "production",
            "app_env",
            "APP_ENV is production.",
            "Set APP_ENV=production for deployed web/worker processes.",
            failure_status="warn",
        ),
        _check(
            len(secret_key) >= 32 and secret_key not in PLACEHOLDER_SECRETS,
            "secret_key",
            "SECRET_KEY is strong and non-placeholder.",
            "Use a random value of at least 32 characters.",
        ),
        _check(
            database_uri.startswith("postgresql://") or database_uri.startswith("postgresql+"),
            "database",
            "Database uses PostgreSQL.",
            "Set DATABASE_URL to a PostgreSQL connection string; SQLite is not production storage.",
        ),
        _check(
            ratelimit_uri and ratelimit_uri != "memory://" and ratelimit_uri.startswith(("redis://", "rediss://")),
            "rate_limits",
            "Rate limits use shared Redis storage.",
            "Attach Render Key Value and set RATELIMIT_STORAGE_URI from its connectionString.",
        ),
        _check(
            _present(config.get("REDIS_URL")) and str(config.get("REDIS_URL")).startswith(("redis://", "rediss://")),
            "redis",
            "REDIS_URL is configured.",
            "Attach Render Key Value and set REDIS_URL from its connectionString.",
        ),
        _check(
            _present(config.get("SUPABASE_URL")) and _present(config.get("SUPABASE_KEY")),
            "supabase",
            "Supabase credentials are configured.",
            "Set SUPABASE_URL and SUPABASE_KEY for durable upload storage.",
        ),
        _check(
            _present(config.get("UPLOAD_STORAGE_BUCKET")) and _present(config.get("PRIVATE_UPLOAD_STORAGE_BUCKET")),
            "storage_buckets",
            "Public and private storage buckets are named.",
            "Expected public uploads bucket and private message-attachment bucket.",
        ),
        _check(
            _present(config.get("BACKUP_STORAGE_BUCKET")),
            "backup_bucket",
            "Backup storage bucket is named.",
            "Set BACKUP_STORAGE_BUCKET for cloud backup uploads.",
        ),
        _check(
            config.get("UPLOAD_KEEP_LOCAL") is False,
            "local_uploads",
            "Local upload retention is disabled.",
            "Set UPLOAD_KEEP_LOCAL=false so local disk is only temporary/cache storage.",
            failure_status="warn",
        ),
        _check(
            int(config.get("MAX_CONTENT_LENGTH") or 0) <= MAX_UPLOAD_BYTES
            and int(config.get("MAX_UPLOAD_BYTES") or 0) <= MAX_UPLOAD_BYTES
            and int(config.get("MESSAGE_ATTACHMENT_MAX_BYTES") or 0) <= MAX_UPLOAD_BYTES,
            "upload_limits",
            "Upload limits are capped at 25MB.",
            "Set MAX_CONTENT_LENGTH, MAX_UPLOAD_BYTES, and MESSAGE_ATTACHMENT_MAX_BYTES to 26214400 or lower.",
        ),
        _check(
            email_backend == "smtp" and delivery_order == ["smtp"],
            "email_backend",
            "Email is SMTP-only.",
            "Set EMAIL_BACKEND=smtp and EMAIL_DELIVERY_ORDER=smtp.",
        ),
        _check(
            all(_present(config.get(key)) for key in ("MAIL_SERVER", "MAIL_PORT", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER")),
            "smtp",
            "SMTP credentials are configured.",
            "Set MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, and MAIL_DEFAULT_SENDER.",
        ),
        _check(
            bool(config.get("WTF_CSRF_ENABLED")),
            "csrf",
            "CSRF protection is enabled.",
            "Set WTF_CSRF_ENABLED=true outside tests.",
        ),
        _check(
            bool(config.get("SESSION_COOKIE_SECURE")) and bool(config.get("REMEMBER_COOKIE_SECURE")),
            "secure_cookies",
            "Session and remember cookies require HTTPS.",
            "ProductionConfig should set SESSION_COOKIE_SECURE and REMEMBER_COOKIE_SECURE.",
        ),
        _check(
            _is_https_url(config.get("PUBLIC_BASE_URL")),
            "public_base_url",
            "PUBLIC_BASE_URL is HTTPS.",
            "Set PUBLIC_BASE_URL to the canonical HTTPS origin.",
        ),
        _check(
            _present(config.get("METRICS_TOKEN")) and config.get("METRICS_TOKEN") not in PLACEHOLDER_SECRETS,
            "metrics_token",
            "Metrics endpoint requires a bearer token.",
            "Set METRICS_TOKEN or protect /metrics at the reverse proxy/network layer.",
            failure_status="warn",
        ),
        _check(
            not config.get("VIRUS_SCAN_ENABLED") or _present(config.get("VIRUS_SCAN_COMMAND")),
            "virus_scan",
            "Virus scan command is configured when scanning is enabled.",
            "Set VIRUS_SCAN_COMMAND when VIRUS_SCAN_ENABLED=true.",
        ),
    ]
    return checks


def production_check_summary(checks):
    failures = sum(1 for check in checks if check.status == "fail")
    warnings = sum(1 for check in checks if check.status == "warn")
    return {"total": len(checks), "failures": failures, "warnings": warnings}
