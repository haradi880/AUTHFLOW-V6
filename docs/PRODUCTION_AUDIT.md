# HaradiBots Production Audit

**Last updated:** 2026-06-04  
**Current readiness score:** 88/100

## Critical Fixes Completed

- Replaced the partial migration chain with a clean baseline plus conversation migration.
- Removed production `db.create_all()` startup behavior; migrations are the production path.
- Added Supabase-first uploads and private message attachments.
- Removed direct nginx `/uploads/` exposure so private files cannot bypass Flask authorization.
- Upload MIME metadata is now server-derived after validation for public image uploads and private message attachments; legacy unsafe attachment MIME values are normalized at download time.
- Moved robotics project files from local-only storage to Supabase-first storage with local fallback.
- Set app/nginx/message upload limits to 25MB.
- Added optional server-side virus scanning hook via `VIRUS_SCAN_ENABLED` and `VIRUS_SCAN_COMMAND`.
- Added Redis-backed rate-limit configuration and route-level limits for auth/API/messages/uploads/search surfaces.
- Added Redis-backed short response caching for anonymous public blog/project feeds.
- Secured Socket.IO notification and conversation rooms using authenticated users and conversation membership.
- Set Socket.IO to use Flask's existing session handling (`manage_session=False`) so realtime tests pass with the current Flask/Werkzeug stack.
- Added conversation-based direct/group messaging with receipts, pagination, private attachments, typing events, retry-safe client IDs, polling fallback, and membership roles.
- Added `/dashboard/content` for uploaded blog management, edit/delete, and restore from soft-delete archive.
- Added stronger public SEO metadata: canonical URLs use `PUBLIC_BASE_URL`, every public page has a fallback Open Graph/Twitter image, JSON-LD metadata is tested, and anonymous public pages avoid unnecessary CSRF/session-cookie churn.
- Tightened browser security headers and CSP: no `unsafe-eval`, explicit `object-src 'none'`, `form-action 'self'`, cross-domain policy blocking, download hardening, and COOP.
- Hardened legacy JWT API tokens with issuer, audience, issued-at, and token IDs.
- Replaced legacy SQLAlchemy primary-key lookups with `db.session.get()` / `db.get_or_404()` and made CI fail on `LegacyAPIWarning`.
- Added `flask production-check` to fail fast on common bad production config: SQLite, weak secrets, missing Redis/Supabase/SMTP, unsafe upload limits, insecure cookies, disabled CSRF, and non-HTTPS canonical URL.
- Added request correlation, structured HTTP request logs, `/readyz` with short successful database-check caching, and Prometheus-style `/metrics` with optional bearer-token protection.
- Added backup archive manifests with SHA-256 checksums, `flask backup-verify`, `flask backup-drill`, backup bucket preflight, and a restore runbook.
- Added accessibility smoke tests, route smoke/performance CLI, concurrent load-check CLI, CI smoke/load gates, feed query-count regression tests, and inbox query-count regression tests.
- Reduced public blog/project feed database work by removing total-count pagination, deferring unused large content columns, and tightening feed query-count regressions.
- Hardened Render/Docker deployment config: `/readyz` health checks, web/worker Redis rate-limit envs, metrics token env, upload limit envs, and container startup production preflight.
- Updated vulnerable dependency pins; `pip-audit -r requirements.txt` now reports no known vulnerabilities.
- Annotated scanner false positives; `bandit -r app -x app/templates` now reports no issues.
- Added CI workflow for compile, dependency audit, Bandit, and pytest.

## Remaining High-Risk Work

- Add external Sentry/OpenTelemetry-style tracing, dashboards, uptime monitoring, and alerting.
- Enable and drill PostgreSQL point-in-time recovery on the chosen production provider.
- Add real browser/E2E coverage for messaging, uploads, mobile responsiveness, and SEO pages.
- Run representative deployed load tests against production PostgreSQL, Redis, object storage, and realistic data volumes.
- Add axe/Lighthouse and visual regression checks for core layouts.
- Add stronger media processing for videos/audio/documents: thumbnails, transcoding/streaming, CDN cache headers, and async processing.
- Add push notifications after the current realtime/polling messaging foundation is stable.
- Expand RBAC beyond admin/member for community moderation and recruiter/company workflows.
- Run `docker compose config` on a machine with Docker installed; this environment does not have Docker available.

## Verification Evidence

- `pytest -q -W error::sqlalchemy.exc.LegacyAPIWarning`: 62 passed.
- `flask --app app:create_app smoke-check --max-p95-ms 10000 --json`: 7 targets, 0 failures.
- `flask --app app:create_app load-check --requests-per-target 2 --concurrency 2 --max-p95-ms 10000 --json`: 7 targets, 14 requests, 0 failures.
- Deployment config tests parse `render.yaml` and `docker-compose.yml` and assert required production env wiring.
- `python -m compileall app tests`: passed.
- `python -m pip_audit -r requirements.txt`: no known vulnerabilities found.
- `python -m bandit -r app -x app/templates -f txt`: no issues identified.
- Messaging hardening tests cover retry idempotency, private attachment header safety, and inbox query-count growth.
- Upload hardening tests cover spoofed client MIME, invalid PDF rejection, safe Supabase content-type metadata, and legacy private attachment MIME normalization.
- SEO metadata tests cover canonical host consistency, Open Graph/Twitter images, JSON-LD types, cacheable generated social image, and no anonymous CSRF token on indexable public detail pages.
- Security header smoke tests cover CSP hardening, cross-domain policy blocking, download hardening, COOP, and the absence of `unsafe-eval`.
- Load-check tests cover concurrent route status/latency summaries and CLI JSON output.
- Public feed performance regression tests now assert `/blogs` stays at five queries or fewer, `/projects` at four queries or fewer, no public-feed `COUNT(*)`, and no full blog body fetch for blog cards.
- Public feed cache tests cover Redis hits and cookie-based bypass for anonymous response caching.
- `APP_ENV=production flask --app app:create_app production-check --json`: 17 checks; current environment fails because production Redis settings are missing (`REDIS_URL` and `RATELIMIT_STORAGE_URI`) and warns that `METRICS_TOKEN` is unset.
- Backup verification: route-created and CLI-created backup archives include `backup_manifest.json`; `flask --app app:create_app backup-verify --path <archive>` and `flask --app app:create_app backup-drill --json` passed in tests.
- Live backup drill: `flask --app app:create_app backup-drill --skip-database --skip-logs --json` passed with no database dump/artifacts and no generated Python cache files.
- Fresh SQLite migration from zero through `20260604_0001` and `20260604_0002`: passed.
- Configured development database upgraded to Alembic revision `20260604_0002`.
- Local environment installed `requirements-dev.txt`; live smoke uses Werkzeug 3.1.8.
- Runtime smoke/load: `/healthz` 200, `/readyz` 200 with database OK, `/metrics` returns counters, `/blogs` 200 without login, `/messages` and `/dashboard/content` redirect to login, and responses include `X-Request-ID`. Repeated live `/readyz` calls return from the successful-result cache after the first database probe. Local smoke/load still show cold-process p95s at about `/readyz` 5.3s, `/blogs` 2.8s, and `/projects` 1.9s, so verify on deployed PostgreSQL/Redis before calling capacity ready.
- `docker-compose.yml` and `render.yaml` parse as valid YAML; full Docker Compose validation was not available locally.

## Deployment Notes

- Production must set `APP_ENV=production`, a strong `SECRET_KEY`, PostgreSQL `DATABASE_URL`, Redis `REDIS_URL`/`RATELIMIT_STORAGE_URI`, Supabase service credentials, and SMTP credentials.
- Supabase buckets remain `uploads` public and `private-uploads` private.
- `UPLOAD_KEEP_LOCAL=false` is the production default; local `uploads/` is temporary/cache only.
- Docker Compose now uses internal PostgreSQL by default and no longer exposes `/uploads` through nginx.
- If virus scanning is enabled, set `VIRUS_SCAN_COMMAND` to a shell-free scanner command such as a ClamAV wrapper; the file path is appended as the final argument.
