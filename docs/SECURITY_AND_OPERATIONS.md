# Security And Operations

This document summarizes current protections, production requirements, deployment notes, and operational risks.

## Current Security Controls

### Authentication

- Passwords are hashed with Werkzeug.
- Registration requires email OTP verification before login.
- Password reset uses OTP tokens.
- Email change uses OTP tokens.
- Failed login attempts increment `failed_login_count`.
- Accounts lock until `locked_until` after too many failures.
- Remember-me sessions use Flask-Login remember cookies.

### Password Policy

`validate_password_strength()` requires:

```text
minimum 10 characters
at least one lowercase letter
at least one uppercase letter
at least one number
at least one symbol
```

### CSRF

Manual CSRF protection is registered in `app/__init__.py`.

Protected:

```text
All non-GET, non-HEAD, non-OPTIONS, non-TRACE web routes
```

Exempt:

```text
Routes whose path starts with /api/
```

Tokens are stored in the session and exposed to templates through `csrf_token()`. `base.html` injects missing hidden CSRF inputs into POST forms and adds `X-CSRFToken` to non-GET fetch calls only on authenticated pages and public pages that actually need POST forms, so indexable read-only pages do not create anonymous CSRF sessions.

### Rate Limiting

Flask-Limiter protects selected routes. Development may use `memory://`, but production startup requires Redis or another shared storage backend through `RATELIMIT_STORAGE_URI`.

| Scope | Routes |
|---|---|
| `register` | Registration |
| `otp`, `otp-json` | OTP resend |
| `login` | Web login |
| `forgot` | Password reset request |
| `password` | Password change |
| `email-change` | Email change start |
| `report` | User report |
| `block` | User block |
| `comments` | Blog comments |
| `api` | Legacy JSON API login and current-user endpoints |
| `messages` | Conversation sends, reads, typing events, group actions, and searches |
| `uploads` | Message attachments |
| `follow` | Follow/unfollow |

Production must use the same shared limiter store across all web and worker processes.

### Upload Safety

Upload protections:

- Folder allowlist: `avatars`, `banners`, `blogs`, `projects`, `devlogs`.
- Extension allowlist: `png`, `jpg`, `jpeg`, `gif`, `webp`.
- DevLog video extension allowlist: `mp4`, `webm`, `mov`.
- 25MB default upload limit at Flask and nginx levels.
- Random hex filename prefix.
- `secure_filename()` for original filename portion.
- Pillow image verification.
- Resize and optimization.
- Server-derived MIME metadata after validation; client-supplied MIME is not trusted for uploaded images or message attachments.
- Optional virus scan hook through `VIRUS_SCAN_ENABLED` and `VIRUS_SCAN_COMMAND`.
- Supabase-first object storage with local disk as temporary/cache storage.
- Private message attachments are fetched through authenticated Flask routes, not public `/uploads` URLs.
- Failed upload cleanup.
- Public upload route only serves allowed non-message folders.

### HTML And Markdown Safety

Blog markdown is rendered in `app/services/content.py` and sanitized through Bleach.

Allowed HTML is limited to selected formatting, code, table, image, link, span, and div tags. Unsupported tags are stripped.

Jinja autoescaping protects templates by default.

### Security Headers

Every response gets the core browser hardening headers:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-Permitted-Cross-Domain-Policies: none`
- `X-Download-Options: noopen`
- `Cross-Origin-Opener-Policy: same-origin`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

The CSP allows current first-party scripts/styles, Google Fonts, the local Socket.IO endpoint, the existing Markdown editor CDN, and the notification audio asset. It explicitly blocks plugins with `object-src 'none'`, restricts forms with `form-action 'self'`, and does not allow `unsafe-eval`.

Configured headers:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Cache behavior:

- Static files are public cached for 7 days.
- Public uploaded files are public cached for 1 day when served through Flask fallback.
- API responses are `no-store`.
- Authenticated GET pages are `no-store`.
- Public anonymous GET pages are public cached for 120 seconds.

## Production Checklist

Before deploying:

- Set `APP_ENV=production`.
- Set a long random `SECRET_KEY`.
- Use PostgreSQL through `DATABASE_URL`.
- Set Redis-backed `RATELIMIT_STORAGE_URI`.
- Set Supabase `SUPABASE_URL`, `SUPABASE_KEY`, `UPLOAD_STORAGE_BUCKET`, and `PRIVATE_UPLOAD_STORAGE_BUCKET`.
- Configure SMTP credentials.
- Set `MAIL_DEFAULT_SENDER`.
- Run `flask db upgrade`.
- Run tests.
- Serve behind HTTPS.
- Use secure cookies, which `ProductionConfig` enables.
- Configure reverse proxy headers if needed.
- Use `/readyz` as the platform health check when supported.
- Rotate default seed passwords.
- Disable or protect demo accounts.
- Set up backups for database and uploads.
- Set up log collection and monitoring.
- Set `METRICS_TOKEN` or restrict `/metrics` at the proxy/network layer.
- Verify the reverse proxy also enforces a 25MB upload limit.

Run the production configuration gate:

```powershell
$env:APP_ENV='production'
.\venv\Scripts\flask.exe --app app:create_app production-check
.\venv\Scripts\flask.exe --app app:create_app smoke-check --base-url https://your-domain.example --iterations 3
.\venv\Scripts\flask.exe --app app:create_app load-check --base-url https://your-domain.example --requests-per-target 25 --concurrency 5 --max-p95-ms 1500
```

The command fails on deployment blockers such as SQLite, weak `SECRET_KEY`, memory-backed rate limits, missing Supabase credentials, missing storage bucket names, upload limits above 25MB, non-SMTP email configuration, missing SMTP credentials, disabled CSRF, insecure cookies, or a non-HTTPS `PUBLIC_BASE_URL`.

### Redis Caching

Redis is used for shared rate limits, Socket.IO fanout, background queues, and short anonymous public-page caching. Set both values in production:

```text
REDIS_URL=redis://...
RATELIMIT_STORAGE_URI=redis://...
PUBLIC_PAGE_CACHE_ENABLED=true
PUBLIC_PAGE_CACHE_SECONDS=120
```

The public-page cache only applies to anonymous `GET` requests without cookies, currently for `/blogs` and `/projects`. Authenticated users bypass it, so private/session state is not cached.

## Deployment Example

PowerShell setup:

```powershell
$env:APP_ENV='production'
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db upgrade
.\venv\Scripts\python.exe -m pytest -q -W error::sqlalchemy.exc.LegacyAPIWarning
.\venv\Scripts\flask.exe --app app:create_app production-check
```

Gunicorn command:

```powershell
.\venv\Scripts\gunicorn.exe -w 4 -b 0.0.0.0:5000 run:app
```

On Windows, Gunicorn is not the normal production choice. Use a Linux host/container for Gunicorn, or choose a Windows-compatible WSGI server if deploying directly on Windows.

The Docker entrypoint runs:

```text
flask --app app:create_app production-check
flask --app app:create_app deploy-db
```

Set `SKIP_PRODUCTION_CHECK=true` only for controlled diagnostics where startup must continue despite known config failures.

## Database Operations

### Local Development

`run.py` in development does:

1. Create the app.
2. Run `db.create_all()` only outside production.
3. Seed demo data if the SQLite database file is new.
4. Start Flask dev server.

This is convenient for local use but does not replace migrations in production.

### Production

Use migrations:

```powershell
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db upgrade
```

Backups:

- Back up the main database.
- Back up uploaded media metadata and Supabase buckets.
- Back up `.env` separately and securely.
- Test restore regularly.

App-created backup archives include `backup_manifest.json` with SHA-256 checksums. Verify archives before trusting them:

```powershell
.\venv\Scripts\flask.exe --app app:create_app backup-verify --path .\uploads\backups\haradi_backup_YYYYMMDD_HHMMSS.zip
.\venv\Scripts\flask.exe --app app:create_app backup-drill --skip-database --json
```

See [Backup And Restore Runbook](BACKUP_RESTORE_RUNBOOK.md) for the restore drill and recovery targets.

## Logging

Logs are written to:

```text
logs/app.log
```

Configuration:

```text
RotatingFileHandler
maxBytes=1,000,000
backupCount=3
```

Use centralized logging in production. Local log files are ignored by git.

Each response includes `X-Request-ID`. If a client sends a valid `X-Request-ID` or `X-Correlation-ID`, the app echoes it; otherwise it generates one. HTTP request logs are JSON-shaped and include method, path, endpoint, status, duration, user id when available, and request id.

## Health And Metrics

Probe endpoints:

```text
GET /healthz
GET /readyz
GET /metrics
GET /api/v1/health
```

Use `/healthz` as a cheap liveness probe. Use `/readyz` as the deployment readiness probe; in production it includes production configuration failures in addition to the database check. Successful database readiness checks are cached in-process for `READINESS_CACHE_SECONDS` seconds and guarded by a per-worker lock, so frequent platform health checks do not stampede the database. `/metrics` emits Prometheus-style process/request counters and duration sums. Set `METRICS_TOKEN` in production or protect `/metrics` at the reverse proxy/network layer.

Run route smoke checks before and after deploy:

```powershell
.\venv\Scripts\flask.exe --app app:create_app smoke-check --max-p95-ms 10000
.\venv\Scripts\flask.exe --app app:create_app smoke-check --base-url https://your-domain.example --iterations 3
```

Run a small concurrent load regression check before release and against the deployed URL:

```powershell
.\venv\Scripts\flask.exe --app app:create_app load-check --requests-per-target 2 --concurrency 2 --max-p95-ms 10000
.\venv\Scripts\flask.exe --app app:create_app load-check --base-url https://your-domain.example --requests-per-target 25 --concurrency 5 --max-p95-ms 1500
```

This is a regression gate, not a full capacity test. Real production load testing still needs production PostgreSQL, Redis, object storage, and representative data.

## Email Operations

There are two email helpers:

| File | Use |
|---|---|
| `app/utils/emailer.py` | Plain-text OTP and welcome emails |
| `app/utils/email.py` | HTML notification emails |

If SMTP credentials are missing, the app logs or skips delivery instead of failing hard.

Operational checks:

- Verify SMTP credentials.
- Use app passwords where required.
- Monitor send failures in logs.
- Consider moving email to a queued worker for high volume.

## Upload Operations

Local upload path defaults to:

```text
uploads/
```

Production requirements:

- Use Supabase Storage or equivalent object storage; local disk is temporary/cache only.
- Store file metadata/object keys in the database.
- Use the public bucket for public avatars, banners, blogs, projects, and devlogs.
- Use the private bucket for message attachments.
- Put public upload serving behind a CDN when traffic grows.
- Keep the reverse proxy and Flask upload limit aligned at 25MB.
- Enable the virus scan hook when the hosting plan can run a scanner.

## Admin Operations

Admin dashboard:

```text
/admin/
```

Admin capabilities:

- View users and counts.
- Suspend/restore non-admin users.
- Review audit logs, login events, and monitoring data.
- Update report status.
- Publish/unpublish draft blogs and projects.

Limitations:

- Admin suspension cannot suspend admin accounts from the panel.
- Report workflow is status-only.
- Admin action coverage should continue expanding as moderation tools grow.

## JWT Operations

JWTs:

- Are signed with `SECRET_KEY`.
- Expire after `JWT_EXPIRATION_HOURS`.
- Include issuer, audience, issued-at, expiry, and token id claims.
- Are checked manually in `/api/user` and `/api/me/xp`.

Operational limitations:

- No token revocation table.
- Rotating `SECRET_KEY` invalidates all tokens and Flask sessions.
- JWT API coverage is small and mostly read-only.

## Known Risks And Hardening Ideas

High value improvements:

- Add pagination parameters to public API lists.
- Expand admin audit coverage for every moderation action.
- Add more detailed content moderation records for actions taken.
- Add account deletion and data export workflow beyond the current JSON export.
- Add async media processing for thumbnails, transcoding, streaming, and CDN optimization.
- Add push notifications on top of the current Socket.IO/polling messaging foundation.
- Add Content-Security-Policy after reviewing inline scripts.
- Add token revocation or short-lived access tokens plus refresh tokens for API auth.
- Add browser E2E tests for blocked-user behavior, message permissions, private attachments, uploads, and SEO pages.

## Incident Response Basics

If a secret leaks:

1. Rotate `SECRET_KEY`.
2. Rotate SMTP password.
3. Rotate database credentials.
4. Restart all app workers.
5. Review logs for suspicious activity.
6. Force password resets if account compromise is suspected.

If bad content is uploaded:

1. Suspend the user from `/admin/`.
2. Remove or unpublish affected content.
3. Delete affected uploaded files from storage.
4. Mark related reports as resolved.
5. Preserve evidence if required before deletion.

If the database is corrupted:

1. Stop writes.
2. Back up the corrupted state for investigation.
3. Restore the latest known-good backup.
4. Re-apply migrations.
5. Verify core flows with tests and manual smoke checks.
