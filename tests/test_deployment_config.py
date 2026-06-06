from pathlib import Path

import yaml


def render_services():
    return yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))["services"]


def env_map(service):
    values = {}
    for item in service.get("envVars", []):
        values[item["key"]] = item
    return values


def test_render_web_uses_readiness_and_required_env_vars():
    web = next(service for service in render_services() if service["type"] == "web")
    env = env_map(web)
    assert web["healthCheckPath"] == "/readyz"
    assert env["METRICS_TOKEN"].get("generateValue") is True
    assert env["MAIL_PORT"]["value"] == "2525"
    assert env["MAIL_FORCE_IPV4"]["value"] == "true"
    for key in (
        "DATABASE_URL",
        "REDIS_URL",
        "RATELIMIT_STORAGE_URI",
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "UPLOAD_STORAGE_BUCKET",
        "PRIVATE_UPLOAD_STORAGE_BUCKET",
        "BACKUP_STORAGE_BUCKET",
        "UPLOAD_KEEP_LOCAL",
        "MAX_CONTENT_LENGTH",
        "MAX_UPLOAD_BYTES",
        "MESSAGE_ATTACHMENT_MAX_BYTES",
        "METRICS_TOKEN",
    ):
        assert key in env


def test_render_worker_gets_redis_and_rate_limit_env_vars():
    worker = next(service for service in render_services() if service["type"] == "worker")
    env = env_map(worker)
    keyvalue = next(service for service in render_services() if service["name"] == "haradibots-redis")
    assert keyvalue["type"] == "keyvalue"
    assert env["METRICS_TOKEN"].get("generateValue") is True
    assert env["MAIL_PORT"]["value"] == "2525"
    assert env["MAIL_FORCE_IPV4"]["value"] == "true"
    assert env["REDIS_URL"]["fromService"]["type"] == "keyvalue"
    assert env["REDIS_URL"]["fromService"]["name"] == "haradibots-redis"
    assert env["RATELIMIT_STORAGE_URI"]["fromService"]["type"] == "keyvalue"
    assert env["RATELIMIT_STORAGE_URI"]["fromService"]["name"] == "haradibots-redis"
    assert env["UPLOAD_KEEP_LOCAL"]["value"] == "false"


def test_docker_compose_web_and_worker_include_runtime_guards():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    for service_name in ("web", "worker"):
        env = compose["services"][service_name]["environment"]
        assert env["APP_ENV"] == "production"
        assert env["REDIS_URL"] == "redis://redis:6379/0"
        assert env["RATELIMIT_STORAGE_URI"] == "redis://redis:6379/0"
        assert env["UPLOAD_KEEP_LOCAL"] == "false"
        assert env["MAX_CONTENT_LENGTH"] == "26214400"
        assert env["MESSAGE_ATTACHMENT_MAX_BYTES"] == "26214400"
        assert "METRICS_TOKEN" in env
