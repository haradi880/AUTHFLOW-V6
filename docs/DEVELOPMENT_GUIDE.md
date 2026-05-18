# Development Guide

This guide covers local setup, common commands, feature workflow, testing, migrations, and troubleshooting.

## Requirements

- Python 3.10 works with the included `venv`.
- Python 3.8+ should work based on dependencies, but the current local environment is Python 3.10.
- SQLite for local development.
- PostgreSQL for production or production-like testing.

## Local Setup

From the project root:

```powershell
cd "g:\Projects\haradi.bot\python auth V3 best one - Copy"
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.env`:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```text
APP_ENV=development
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///platform.db
UPLOAD_FOLDER=uploads
```

Start the app:

```powershell
python run.py
```

The app listens on:

```text
http://127.0.0.1:5000
```

`run.py` creates missing tables. If the local SQLite database is new, it seeds demo data.

## Common Commands

```powershell
# Run the app
.\venv\Scripts\python.exe run.py

# Run tests
.\venv\Scripts\python.exe -m pytest -q

# Run one test file
.\venv\Scripts\python.exe -m pytest tests\test_app_smoke.py -q

# Re-run seed logic
.\venv\Scripts\python.exe populate_data.py

# Use Flask CLI
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe --help

# Initialize categories and default admin through CLI
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe init-db

# Apply migrations
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db upgrade

# Generate a migration after model changes
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db migrate -m "describe change"
```

## Recommended Workflow

1. Read the relevant route in `app/routes/`.
2. Check the model fields and relationships in `app/models/__init__.py`.
3. Move reusable logic into `app/services/` when a rule is used in multiple routes.
4. Keep helpers in `app/utils/` focused on technical concerns such as uploads, email, decorators, and rate limiting.
5. Update templates under `app/templates/` and assets under `app/static/`.
6. Add or update tests in `tests/`.
7. Run `pytest -q`.
8. Update docs when behavior, routes, environment variables, data model, or setup changes.

## Adding A Model Or Field

1. Edit `app/models/__init__.py`.
2. Add relationships and constraints at the same time as the new fields.
3. Generate a migration:

```powershell
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db migrate -m "add new field"
```

4. Inspect the generated migration before applying it.
5. Apply it:

```powershell
.\venv\Scripts\flask.exe db upgrade
```

6. Add tests that create, update, and read the new data.

Local `db.create_all()` may make new tables appear during development, but migrations are still the source of truth for shared databases.

## Adding A Web Route

1. Choose the blueprint in `app/routes/`.
2. Add `@login_required`, `@admin_required`, or `@owner_required(...)` where needed.
3. For write routes, rely on normal CSRF behavior unless the route is intentionally under `/api/`.
4. Validate form fields and file uploads before committing.
5. Use `flash()` plus redirect for normal web form flows.
6. Return JSON only for AJAX/API-like interactions.
7. Add a template under `app/templates/` if the route renders a page.
8. Add smoke or behavior tests.

## Adding A JSON API Endpoint

1. Put public/JWT endpoints in `app/routes/api.py`.
2. Decide auth type: public, JWT, or browser session.
3. Keep response payloads explicit with helper functions.
4. Return clear status codes: `400`, `401`, `403`, `404`, or `429` where appropriate.
5. Document the endpoint in `docs/API_REFERENCE.md`.
6. Add tests for success and failure paths.

## Adding A Template

Most pages extend `base.html`:

```jinja
{% extends "base.html" %}
{% block title %}Page Title - AuthFlow{% endblock %}
```

Common components:

```text
components/navbar.html
components/sidebar.html
components/breadcrumb.html
components/blog_card.html
components/skeleton.html
```

Remember:

- POST forms need `_csrf_token`. `base.html` injects it automatically on submit if missing, but explicit hidden inputs are clearer in important forms.
- Use `url_for(...)` for internal links.
- Use `upload_url` filter or model URL properties for uploaded media.
- Use `.js-local-time` with ISO datetime strings for browser-local time rendering.

## Frontend Notes

Global behavior:

- `base.html` creates `window.AuthFlow.csrfToken`.
- `base.html` wraps `window.fetch` and adds `X-CSRFToken` to non-GET requests.
- `main.js` exposes `window.AuthFlow.formatLocalTime()` and `formatLocalTimes()`.
- Toasts are available through `window.toast`.

Feature scripts:

```text
auth.js        Auth forms and OTP input
dashboard.js   Sidebar, active nav, admin table search
blog.js        Like/bookmark AJAX
devlogs.js     DevLog composer, infinite loading, likes, reposts, bookmarks, comments, pins
profile.js     Follow button, tabs, copy profile link
faq.js         FAQ category filtering, search, expand/collapse
feed.js        Feed filter helper
editor.js      Markdown draft/preview helper
components.js  Dropdowns, modals, tooltips
```

Some features currently use inline template scripts. When a script grows or is reused, move it into `app/static/js/`.

## Testing

Tests live in `tests/test_app_smoke.py`.

The suite currently verifies:

- Public pages render.
- Dynamic and static cache headers.
- Remember-me cookie behavior.
- Bookmarks page.
- Profile completion and featured content update.
- Public API and tag suggestions.
- DevLogs feed rendering, creation, and AJAX interactions.
- OTP resend.
- Admin moderation and suspension.
- XP level progress and daily duplicate prevention.
- Project stars awarding XP.

Run:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Testing config disables CSRF and uses in-memory SQLite by default:

```text
APP_ENV=testing
TEST_DATABASE_URL=sqlite:///:memory:
```

## Seeding

`populate_data.py` is idempotent. It uses `get_or_create()` and can be safely rerun.

It creates:

- Categories.
- Tags.
- Admin account.
- Demo user.
- Welcome blog.
- Sample project.
- Starter messages and notification.

Environment overrides:

```text
ADMIN_EMAIL
ADMIN_PASSWORD
DEMO_PASSWORD
```

## Email In Development

If SMTP credentials are missing:

- `app/utils/emailer.py` logs and skips OTP/welcome email delivery.
- `app/utils/email.py` logs mock HTML email delivery.

This lets local development work without a mail server. To test real OTP email, set:

```text
MAIL_SERVER
MAIL_PORT
MAIL_USE_TLS
MAIL_USERNAME
MAIL_PASSWORD
MAIL_DEFAULT_SENDER
```

## Uploads In Development

Uploads are saved under:

```text
uploads/avatars
uploads/banners
uploads/blogs
uploads/projects
uploads/devlogs
```

The app creates these folders on startup.

Allowed file extensions:

```text
png, jpg, jpeg, gif, webp
```

DevLog media also allows configured video extensions:

```text
mp4, webm, mov
```

Pillow verifies images and resizes large files. Failed uploads are removed.

## Troubleshooting

### `ModuleNotFoundError`

Use the project virtualenv:

```powershell
.\venv\Scripts\Activate.ps1
.\venv\Scripts\python.exe run.py
```

If needed:

```powershell
pip install -r requirements.txt
```

### Invalid CSRF Token

For web forms:

- Make sure the page extends `base.html`.
- Include `<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">` for explicit POST forms.
- For AJAX, use `fetch()` after `base.html` loads, or send `X-CSRFToken`.

For tests:

- Use `create_app("testing")`, which disables CSRF.

### Database Looks Stale

For local SQLite:

- `run.py` calls `db.create_all()`.
- `ensure_runtime_schema()` adds some missing user columns for old local SQLite databases.
- If schema drift is severe, back up and recreate the local `.db`.

For shared/prod databases:

```powershell
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db upgrade
```

### Emails Not Arriving

Check:

- `MAIL_USERNAME` and `MAIL_PASSWORD` are set.
- SMTP provider allows app passwords or SMTP login.
- `MAIL_DEFAULT_SENDER` is valid.
- `logs/app.log` for send failures.

### Uploaded Image Not Showing

Check:

- The file exists under `UPLOAD_FOLDER/<folder>/`.
- The folder is one of `avatars`, `banners`, `blogs`, or `projects`.
- The database stores only the filename, not the full path.
- The template uses `/uploads/<folder>/<filename>` through model properties or `upload_url`.

### Rate Limit During Manual Testing

The limiter is process-local and keyed by scope, user/ip, and endpoint. Restarting the dev server clears it.

## Conventions

- Keep route functions small enough to read.
- Prefer services for reusable business rules.
- Prefer SQLAlchemy query APIs over raw SQL unless a migration needs raw SQL.
- Add tests for auth, admin, uploads, messaging, API, and XP changes.
- Never commit `.env`, local databases, uploaded media, logs, caches, or virtualenv files.
- Keep documentation updated with route, env, schema, and workflow changes.
