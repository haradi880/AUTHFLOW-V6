# HaradiBots Security Audit Report

**Last updated:** 2026-06-04  
**Status:** Active hardening complete for current P0/P1 blockers; production readiness still requires external monitoring, recovery drills, E2E, and media pipeline work.

## Critical Issues Fixed

- CSRF protection is centralized with Flask-WTF and global fetch/form helpers.
- Public indexable pages no longer emit CSRF tokens or anonymous session cookies just for read-only crawler traffic.
- Destructive blog/project/account operations use authorization checks, password confirmation where required, audit logs, and soft-delete/archive behavior.
- Uploads use randomized names, image validation, size limits, path traversal protection, server-derived MIME metadata, Supabase-first storage, and optional virus scanning.
- Message attachments are private through authenticated routes and no longer publicly served from `/uploads/messages`.
- Message attachment download headers now sanitize legacy unsafe filenames before setting `Content-Disposition`.
- Message attachment responses normalize MIME from validated extension/content rules, so legacy rows cannot force unsafe inline `text/html` display.
- nginx no longer serves `/uploads` directly.
- Socket.IO rooms for notifications and conversations use authenticated user state and membership checks.
- Socket.IO uses Flask session handling instead of managed session copies for compatibility with the current Flask stack.
- Legacy API login and content endpoints now have route-level rate limits.
- JWTs now include issuer, audience, issued-at, expiry, and jti claims.
- Legacy SQLAlchemy primary-key lookups were replaced with SQLAlchemy 2-safe helpers, and CI now treats `LegacyAPIWarning` as a failure.
- `flask production-check` now validates production-critical config before deploy.
- Request IDs, structured HTTP request logs, `/readyz` with short successful database-check caching, and Prometheus-style `/metrics` were added.
- Backup archives now include checksum manifests and can be verified with `flask backup-verify`; `flask backup-drill` creates and verifies a new archive from CLI.
- Accessibility smoke checks, route smoke checks, concurrent load-check CLI, feed query-count regression tests, and inbox query-count regression tests were added.
- SEO metadata checks now cover canonical URLs, Open Graph/Twitter images, JSON-LD, and public-page cookie behavior.
- Conversation sends now deduplicate retries by `client_id`, and the chat UI exposes connection state plus retry controls for failed sends.
- Public blog/project feeds now avoid total-count pagination and unnecessary large content-column loads.
- Browser security headers and CSP are tighter: no `unsafe-eval`, explicit `object-src 'none'`, `form-action 'self'`, cross-domain policy blocking, download hardening, and COOP.
- Redis-backed anonymous public-feed response caching reduces repeated database reads for crawler/visitor traffic.
- Render/Docker deployment config now uses `/readyz`, passes required Redis/upload/metrics envs, and container startup runs production preflight before migrations.
- Dependency pins have been updated; `pip-audit -r requirements.txt` reports no known vulnerabilities.
- Bandit static analysis reports no current issues.

## Medium Issues Still Open

- Full RBAC/moderation roles are not complete beyond admin/member and conversation group roles.
- Observability now has request IDs, readiness, metrics, and structured request logs; external tracing, dashboards, uptime checks, and alerting still need deployment.
- Media handling needs async thumbnail/transcoding/streaming support for video/audio/documents.
- E2E, full browser accessibility, SEO crawl, and representative deployed load tests are still limited.
- Browser E2E, axe/Lighthouse, visual regression, and real production-capacity tests remain limited.

## Current Evidence

- `pytest -q -W error::sqlalchemy.exc.LegacyAPIWarning`: 62 passed.
- `flask --app app:create_app smoke-check --max-p95-ms 10000 --json`: 7 targets, 0 failures.
- `flask --app app:create_app load-check --requests-per-target 2 --concurrency 2 --max-p95-ms 10000 --json`: 7 targets, 14 requests, 0 failures.
- Deployment config tests parse Render/Docker config and assert required production env wiring.
- `python -m compileall app tests`: passed.
- `python -m pip_audit -r requirements.txt`: no known vulnerabilities found.
- `python -m bandit -r app -x app/templates -f txt`: no issues identified.
- Focused messaging/storage/performance tests: 6 passed.
- Focused upload/attachment hardening tests: 6 passed.
- Focused SEO metadata tests: 3 passed.
- Focused load-check tests: 2 passed.
- Feed performance regression tests enforce reduced public-feed query counts and prevent full blog-body loading on cards.
- Security header smoke tests verify CSP hardening, extra browser safety headers, and absence of `unsafe-eval`.
- Public feed cache tests verify Redis cache hits and cookie-based bypass.
- Fresh migration from empty SQLite through current revisions: passed.
- Live smoke: `/healthz` 200, `/blogs` 200 public, `/messages` and `/dashboard/content` redirect to login.
- `APP_ENV=production flask --app app:create_app production-check --json`: command works; current environment intentionally fails until production Redis env vars are set and warns until `METRICS_TOKEN` is set or `/metrics` is proxy-protected.
- Live observability smoke: `/readyz` 200 with database OK, repeated `/readyz` calls use the short successful-result cache, `/metrics` returns counters, and responses include `X-Request-ID`.
- Live backup drill: `flask --app app:create_app backup-drill --skip-database --skip-logs --json` passed and excluded database dumps/artifacts plus generated Python cache files.

## Next Security Work

- Run a real backup/restore drill for PostgreSQL PITR and Supabase Storage using the documented runbook.
- Add Sentry/OpenTelemetry or equivalent monitoring.
- Add Playwright/axe tests for auth, uploads, public SEO pages, and messaging.
- Implement moderator/company/recruiter/community permissions as formal RBAC policies.
