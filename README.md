# AuthFlow Developer Platform

AuthFlow is a Flask-based developer community platform. It combines email-based account verification, public developer profiles, blogs, projects, follows, notifications, direct messages, admin moderation, local uploads, a small JWT API, and an XP/level system.

This repository is a traditional server-rendered Flask app with Jinja templates and vanilla JavaScript. The application factory lives in `app/__init__.py`, routes are split by feature under `app/routes/`, and SQLAlchemy models are centralized in `app/models/__init__.py`.

## What The App Does

- Account registration, OTP email verification, login, logout, remember-me sessions, password reset, failed-login lockout, and email change verification.
- Developer profiles with avatar, banner, bio, headline, location, links, skills, featured blog/project, profile completion, followers, profile views, blocking, reporting, and export.
- Blog publishing with drafts, markdown rendering, categories, tags, thumbnails, comments, likes, bookmarks, feeds, search, and related posts.
- Project showcases with drafts, categories, tags, thumbnail, gallery images, GitHub/demo links, stars, feeds, and related projects.
- DevLogs build-in-public feed with short updates, progress, milestones, hashtags, media, likes, comments, reposts, bookmarks, pinned logs, infinite loading, and XP.
- Social layer with follows, followers/following pages, notification feed, unread badges, and lightweight polling.
- Direct messages with inbox, chat view, AJAX send, polling, unread counts, block checks, and per-user message permissions.
- Admin dashboard for user suspension, report status updates, and draft content review.
- Gamification through XP rewards, daily caps, source-level duplicate protection, levels, and profile progress.
- Public JSON API for profiles, blogs, projects, login, current user details, and XP progress.

## Quick Start

Use the project virtual environment if it already exists:

```powershell
cd "g:\Projects\haradi.bot\python auth V3 best one - Copy"
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
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

On a new local SQLite database, `run.py` creates missing tables and seeds demo data through `populate_data.py`.

Default local demo accounts created by the seed script:

```text
Admin: admin@authflow.local / change-me-admin
User:  demo@authflow.local / demo12345!
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
MAX_CONTENT_LENGTH=16777216
MAX_LOGIN_ATTEMPTS=5
LOGIN_LOCK_MINUTES=15
ITEMS_PER_PAGE=12
JWT_EXPIRATION_HOURS=24
TEST_DATABASE_URL=sqlite:///:memory:
```

For production, set `APP_ENV=production`, use a strong `SECRET_KEY`, configure real SMTP credentials, prefer PostgreSQL through `DATABASE_URL`, run migrations, and move uploads to persistent storage.

## Documentation Map

- [Project Documentation](PROJECT_DOCUMENTATION.md): complete project overview, feature guide, route map, and maintenance notes.
- [Architecture](docs/ARCHITECTURE.md): app factory, blueprints, service boundaries, request flow, uploads, notifications, and XP flow.
- [API Reference](docs/API_REFERENCE.md): public API, JWT endpoints, session-backed JSON endpoints, request/response shapes, and auth notes.
- [Database Schema](docs/DATABASE_SCHEMA.md): models, tables, relationships, constraints, and lifecycle notes.
- [Development Guide](docs/DEVELOPMENT_GUIDE.md): setup, commands, tests, migrations, feature workflow, troubleshooting, and conventions.
- [Security And Operations](docs/SECURITY_AND_OPERATIONS.md): security controls, production checklist, deployment, logging, backups, and operational risks.

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
uploads/                  Local runtime media, ignored by git
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
/messages                 Inbox
/messages/<username>      Chat
/settings                 Preferences, password, email change, export
/notifications            Notification feed
/admin/                   Admin dashboard
/search?q=term            Search blogs, projects, and users
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
.\venv\Scripts\python.exe -m pytest -q

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

- `run.py` calls `db.create_all()` to make local development forgiving. Use migrations for shared or production schema changes.
- CSRF is enforced manually for non-API write requests. `base.html` injects hidden CSRF fields into POST forms and adds `X-CSRFToken` to non-GET `fetch()` calls.
- API routes under `/api/` are exempt from the web CSRF check. JWT endpoints validate bearer tokens manually.
- Uploads are restricted to `avatars`, `banners`, `blogs`, and `projects`, validated with Pillow, resized, and stored under `UPLOAD_FOLDER`.
- DevLog uploads use the `devlogs` folder and support verified images plus configured short-form video extensions.
- The in-memory rate limiter is useful for one-process development. Use a shared store such as Redis before horizontally scaling.
- Email delivery is skipped or logged when SMTP credentials are missing, so local development works without mail credentials.

## Current Test Coverage

The test suite covers:

- Public pages and cache headers
- Remember-me login cookie behavior
- Bookmarks and profile editing
- Public API and tag suggestions
- DevLogs feed creation and AJAX interactions
- OTP resend behavior
- Admin moderation actions
- XP daily caps, levels, and project-star rewards

Run the suite after documentation or code changes:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```
