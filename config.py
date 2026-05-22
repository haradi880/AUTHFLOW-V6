import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _database_uri() -> str:
    uri = os.getenv("DATABASE_URL")
    if uri:
        if uri.startswith("postgres://"):
            return uri.replace("postgres://", "postgresql://", 1)
        return uri
    return f"sqlite:///{BASE_DIR / 'platform.db'}"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    APP_NAME = os.getenv("APP_NAME") or "AUTHFLOW"
    PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "https://haradibots.onrender.com").rstrip("/")
    HOST = os.getenv("HOST") or "0.0.0.0"
    PORT = _env_int("PORT", 5000)
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    _upload_folder = Path(os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads")))
    UPLOAD_FOLDER = str(_upload_folder if _upload_folder.is_absolute() else BASE_DIR / _upload_folder)
    MAX_CONTENT_LENGTH = _env_int("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_BYTES", MAX_CONTENT_LENGTH)
    MAX_IMAGE_PIXELS = _env_int("MAX_IMAGE_PIXELS", 24_000_000)
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
    MESSAGE_ATTACHMENT_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "zip"}
    MESSAGE_ATTACHMENT_MAX_BYTES = _env_int("MESSAGE_ATTACHMENT_MAX_BYTES", 5 * 1024 * 1024)

    PERMANENT_SESSION_LIFETIME = timedelta(days=_env_int("SESSION_DAYS", 30))
    REMEMBER_COOKIE_DURATION = timedelta(days=_env_int("REMEMBER_DAYS", 30))
    SESSION_REFRESH_EACH_REQUEST = True
    REMEMBER_COOKIE_REFRESH_EACH_REQUEST = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = _env_bool("WTF_CSRF_ENABLED", True)

    MAIL_SERVER = os.getenv("MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = _env_int("MAIL_PORT", 587)
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)
    MAIL_TIMEOUT = _env_float("MAIL_TIMEOUT", 10)
    MAIL_FORCE_IPV4 = _env_bool("MAIL_FORCE_IPV4", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER") or MAIL_USERNAME or "noreply@example.com"
    MAIL_SENDER_NAME = os.getenv("MAIL_SENDER_NAME") or APP_NAME
    MAIL_SUPPRESS_SEND = _env_bool("MAIL_SUPPRESS_SEND", False)

    MAIL_BACKUP_SERVER = os.getenv("MAIL_BACKUP_SERVER")
    MAIL_BACKUP_PORT = _env_int("MAIL_BACKUP_PORT", 587)
    MAIL_BACKUP_USE_TLS = _env_bool("MAIL_BACKUP_USE_TLS", True)
    MAIL_BACKUP_USE_SSL = _env_bool("MAIL_BACKUP_USE_SSL", False)
    MAIL_BACKUP_USERNAME = os.getenv("MAIL_BACKUP_USERNAME")
    MAIL_BACKUP_PASSWORD = os.getenv("MAIL_BACKUP_PASSWORD")
    MAIL_BACKUP_DEFAULT_SENDER = os.getenv("MAIL_BACKUP_DEFAULT_SENDER") or MAIL_DEFAULT_SENDER

    EMAIL_BACKEND = (os.getenv("EMAIL_BACKEND") or "auto").lower()
    EMAIL_DELIVERY_ORDER = os.getenv("EMAIL_DELIVERY_ORDER") or "smtp,backup_smtp,resend,sendgrid,file"
    EMAIL_FILE_FALLBACK = _env_bool("EMAIL_FILE_FALLBACK", False)
    EMAIL_OUTBOX_FOLDER = os.getenv("EMAIL_OUTBOX_FOLDER") or str(BASE_DIR / "logs" / "email_outbox")
    EMAIL_ASYNC = _env_bool("EMAIL_ASYNC", True)
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    RESEND_FROM = os.getenv("RESEND_FROM") or MAIL_DEFAULT_SENDER
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    SENDGRID_FROM = os.getenv("SENDGRID_FROM") or MAIL_DEFAULT_SENDER

    MAX_LOGIN_ATTEMPTS = _env_int("MAX_LOGIN_ATTEMPTS", 5)
    LOGIN_LOCK_MINUTES = _env_int("LOGIN_LOCK_MINUTES", 15)
    ITEMS_PER_PAGE = _env_int("ITEMS_PER_PAGE", 12)
    JWT_EXPIRATION_HOURS = _env_int("JWT_EXPIRATION_HOURS", 24)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI") or "memory://"
    REDIS_URL = os.getenv("REDIS_URL") or os.getenv("RATELIMIT_STORAGE_URI") or "redis://localhost:6379/0"
    TASK_QUEUE_ASYNC = _env_bool("TASK_QUEUE_ASYNC", False)
    NOTIFICATION_MAX_RETRIES = _env_int("NOTIFICATION_MAX_RETRIES", 3)
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    UPLOAD_STORAGE_BUCKET = os.getenv("UPLOAD_STORAGE_BUCKET") or "uploads"
    BACKUP_STORAGE_BUCKET = os.getenv("BACKUP_STORAGE_BUCKET") or "backups"
    BACKUP_KEEP_LOCAL = _env_int("BACKUP_KEEP_LOCAL", 20)

    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }


class DevelopmentConfig(Config):
    DEBUG = True
    EMAIL_FILE_FALLBACK = _env_bool("EMAIL_FILE_FALLBACK", True)


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    MAIL_SUPPRESS_SEND = True
    EMAIL_ASYNC = False
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
