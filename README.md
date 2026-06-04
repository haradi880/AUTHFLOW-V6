# HaradiBots Developer Platform

HaradiBots is a Flask-based developer community platform. It combines email-based account verification, public developer profiles, blogs, projects, follows, notifications, conversation messaging, admin moderation, Supabase-backed uploads, a small JWT API, and an XP/level system.

This repository is a traditional server-rendered Flask app with Jinja templates and vanilla JavaScript. The application factory lives in `app/__init__.py`, routes are split by feature under `app/routes/`, and SQLAlchemy models are centralized in `app/models/__init__.py`.

## What The App Does

- Account registration, OTP email verification, login, logout, remember-me sessions, password reset, failed-login lockout, and email change verification.
- Developer profiles with avatar, banner, bio, headline, location, links, skills, featured blog/project, profile completion, followers, profile views, blocking, reporting, and export.
- Blog publishing with drafts, markdown rendering, categories, tags, thumbnails, comments, likes, bookmarks, feeds, search, and related posts.
- Project showcases with drafts, categories, tags, thumbnail, gallery images, GitHub/demo links, stars, feeds, and related projects.
- DevLogs build-in-public feed with short updates, progress, milestones, hashtags, media, likes, comments, reposts, bookmarks, pinned logs, infinite loading, and XP.
- Social layer with follows, followers/following pages, notification feed, unread badges, and lightweight polling.
- Conversation messaging with direct chats, group chats, private attachments, receipts, typing events, unread counts, retry-safe client IDs, Socket.IO events, and polling fallback.
- Public SEO metadata with canonical production URLs, JSON-LD, sitemap/robots support, fallback social preview images, and cache-friendly anonymous public pages.
- Admin dashboard for user suspension, report status updates, and draft content review.
- Gamification through XP rewards, daily caps, source-level duplicate protection, levels, and profile progress.
- Public JSON API for profiles, blogs, projects, login, current user details, and XP progress.

## Quick Start

Use the project virtual environment if it already exists:

```powershell
cd "g:\Projects\haradi.bot\python auth V7 - Copy"
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python run.py
```

Open:

```text
http://127.0.0.1:5000
```

Run tests:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

On a new local SQLite database, `run.py` can bootstrap missing tables for development only. Production uses Alembic migrations only.

Default local demo accounts created by the seed script:

```text
Admin: admin@haradibots.local / change-me-admin
User:  demo@haradibots.local / demo12345!
```

Set `ADMIN_PASSWORD` and `DEMO_PASSWORD` before seeding if you want different local passwords.

## Environment

Copy `.env.example` to `.env` and update values:

```text
APP_ENV=development
FLASK_APP=run.py
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///platform.db
UPLOAD_FOLDER=uploads
SUPABASE_URL=
SUPABASE_KEY=
UPLOAD_STORAGE_BUCKET=uploads
PRIVATE_UPLOAD_STORAGE_BUCKET=private-uploads
UPLOAD_KEEP_LOCAL=false
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=noreply@example.com
ADMIN_PASSWORD=change-me-admin
WTF_CSRF_ENABLED=true
SESSION_DAYS=30
REMEMBER_DAYS=30
```

Useful optional settings supported by `config.py`:

```text
MAX_CONTENT_LENGTH=26214400
MAX_UPLOAD_BYTES=26214400
MESSAGE_ATTACHMENT_MAX_BYTES=26214400
VIRUS_SCAN_ENABLED=false
VIRUS_SCAN_COMMAND=
MAX_LOGIN_ATTEMPTS=5
LOGIN_LOCK_MINUTES=15
ITEMS_PER_PAGE=12
JWT_EXPIRATION_HOURS=24
JWT_ISSUER=haradibots
JWT_AUDIENCE=haradibots-api
TEST_DATABASE_URL=sqlite:///:memory:
```

For production, set `APP_ENV=production`, use a strong `SECRET_KEY`, configure real SMTP credentials, use PostgreSQL through `DATABASE_URL`, set Redis-backed `RATELIMIT_STORAGE_URI`, set `METRICS_TOKEN`, run migrations, and configure Supabase Storage. `READINESS_CACHE_SECONDS` controls the short in-process cache for successful `/readyz` database checks; keep it low, such as 10 seconds. `PUBLIC_PAGE_CACHE_SECONDS` controls short Redis caching for anonymous public feed pages such as `/blogs` and `/projects`.

## Documentation Map

- [Project Documentation](PROJECT_DOCUMENTATION.md): complete project overview, feature guide, route map, and maintenance notes.
- [Architecture](docs/ARCHITECTURE.md): app factory, blueprints, service boundaries, request flow, uploads, notifications, and XP flow.
- [API Reference](docs/API_REFERENCE.md): public API, JWT endpoints, session-backed JSON endpoints, request/response shapes, and auth notes.
- [Database Schema](docs/DATABASE_SCHEMA.md): models, tables, relationships, constraints, and lifecycle notes.
- [Development Guide](docs/DEVELOPMENT_GUIDE.md): setup, commands, tests, migrations, feature workflow, troubleshooting, and conventions.
- [Security And Operations](docs/SECURITY_AND_OPERATIONS.md): security controls, production checklist, deployment, logging, backups, and operational risks.
- [Backup And Restore Runbook](docs/BACKUP_RESTORE_RUNBOOK.md): backup creation, verification, restore drill, and recovery targets.

## Project Structure

```text
app/
  __init__.py             App factory, blueprints, CSRF, headers, CLI, uploads
  extensions.py           SQLAlchemy, Flask-Login, Flask-Migrate instances
  models/                 All SQLAlchemy models and many-to-many tables
  routes/                 Web routes, JSON routes, admin routes, API routes
  services/               Auth, content, gamification, notification logic
  utils/                  Uploads, decorators, helpers, email, rate limiting
  static/
    css/                  Page, layout, component, feed, profile, auth styles
    js/                   Toasts, forms, editor, feed, profile, dashboard JS
  templates/              Jinja pages, partials, email templates, errors
migrations/               Alembic/Flask-Migrate configuration and revisions
tests/                    Pytest smoke, feature, API, admin, and XP tests
uploads/                  Local temporary/cache media, ignored by git
instance/                 Local runtime data, ignored by git
logs/                     Runtime logs, ignored by git
config.py                 Environment-driven configuration
populate_data.py          Idempotent demo data seeding
run.py                    Development entry point and local DB preparation
```

## Important Web Routes

```text
/                         Dashboard for logged-in users, blog feed for guests
/register                 Register account
/verify-signup            Verify signup OTP
/login                    Log in
/logout                   Log out
/forgot                   Start password reset
/reset-verify             Verify reset OTP
/new-password             Set new password
/blogs                    Blog feed
/blog/<slug>              Blog detail
/devfeed                  Live developer activity feed
/devlogs                  DevLog feed and composer
/devlogs/<id>             DevLog detail
/upload/blog              Create blog
/projects                 Project feed
/project/<slug>           Project detail
/upload/project           Create project
/<username>               Public profile
/profile/edit             Edit current profile
/bookmarks                Current user's bookmarked blogs
/following                Feed from followed users
/dashboard/content        Current user's blog manager
/messages                 Conversation inbox
/messages/<username>      Direct conversation starter
/messages/c/<public_id>   Conversation chat
/settings                 Preferences, password, email change, export
/notifications            Notification feed
/admin/                   Admin dashboard
/search?q=term            Search blogs, projects, and users
/healthz                  Liveness probe
/readyz                   Readiness probe with database/config checks and short successful-result cache
/metrics                  Prometheus-style process metrics
/faq                      Interactive help center
/support                  UPI support page
```

## Public API

Public endpoints:

```text
GET  /api/profiles
GET  /api/profiles/<username>
GET  /api/blogs
GET  /api/blogs/<slug>
GET  /api/projects
GET  /api/projects/<slug>
POST /api/login
```

Authenticated JWT endpoints:

```text
GET /api/user
GET /api/me/xp
```

Use the token from `/api/login`:

```text
Authorization: Bearer <token>
```

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for payloads and session-backed AJAX endpoints.

## Common Commands

```powershell
# Start the app
.\venv\Scripts\python.exe run.py

# Seed or re-check demo data
.\venv\Scripts\python.exe populate_data.py

# Run tests
.\venv\Scripts\python.exe -m pytest -q -W error::sqlalchemy.exc.LegacyAPIWarning

# Run security/dependency checks
.\venv\Scripts\python.exe -m pip_audit -r requirements.txt
.\venv\Scripts\python.exe -m bandit -r app -x app/templates -f txt

# Check production-critical configuration before deploy
.\venv\Scripts\flask.exe --app app:create_app production-check

# Verify a local backup archive
.\venv\Scripts\flask.exe --app app:create_app backup-verify --path .\uploads\backups\haradi_backup_YYYYMMDD_HHMMSS.zip

# Create and verify a local backup drill archive
.\venv\Scripts\flask.exe --app app:create_app backup-drill --skip-database --json

# Run local route smoke/performance checks
.\venv\Scripts\flask.exe --app app:create_app smoke-check --max-p95-ms 10000
.\venv\Scripts\flask.exe --app app:create_app load-check --requests-per-target 2 --concurrency 2 --max-p95-ms 10000

# Run smoke checks against a deployed URL
.\venv\Scripts\flask.exe --app app:create_app smoke-check --base-url https://your-domain.example --iterations 3
.\venv\Scripts\flask.exe --app app:create_app load-check --base-url https://your-domain.example --requests-per-target 25 --concurrency 5 --max-p95-ms 1500

# Initialize categories/admin from Flask CLI
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe init-db

# Apply migrations
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db upgrade

# Create a migration after model changes
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db migrate -m "describe change"
```

## Development Notes

- Use migrations for schema changes. Production startup does not create tables with `db.create_all()`.
- The Docker entrypoint runs `flask --app app:create_app production-check` before migrations unless `SKIP_PRODUCTION_CHECK=true`.
- CSRF is enforced manually for non-API write requests. `base.html` injects hidden CSRF fields into POST forms and adds `X-CSRFToken` to non-GET `fetch()` calls.
- API routes under `/api/` are exempt from the web CSRF check. JWT endpoints validate bearer tokens manually.
- Uploads are restricted to approved folders, capped at 25MB by default, validated server-side, assigned server-derived MIME metadata, optionally virus scanned, then uploaded to Supabase Storage when configured. `UPLOAD_FOLDER` is a temporary/cache directory; with `UPLOAD_KEEP_LOCAL=false`, local copies are removed after Supabase upload succeeds.
- DevLog uploads use the `devlogs` folder and support verified images plus configured short-form video extensions.
- Rate limits use Flask-Limiter. Development may use `memory://`; production must use Redis through `RATELIMIT_STORAGE_URI`. When `REDIS_URL` is set, anonymous public feed pages use Redis for short-lived response caching to reduce repeated database reads.
- Responses include `X-Request-ID`; request timing/counts are exposed through `/metrics`, protected by `METRICS_TOKEN` when set.
- Email delivery is skipped or logged when SMTP credentials are missing, so local development works without mail credentials.

## Current Test Coverage

The test suite covers:

- Public pages and cache headers
- Remember-me login cookie behavior
- Bookmarks and profile editing
- Public API and tag suggestions
- DevLogs feed creation and AJAX interactions
- OTP resend behavior
- Blog content management, edit/delete authorization, and soft-delete restore
- Conversation direct/group messaging, private attachments, and API JWT behavior
- Production configuration checks
- Request IDs, readiness, and metrics endpoints
- Backup manifest and verification command
- Accessibility basics and route smoke/load/performance checks
- Admin moderation actions
- XP daily caps, levels, and project-star rewards

Run the suite after documentation or code changes:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```
