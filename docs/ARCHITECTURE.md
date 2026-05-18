# Architecture

This document explains how AuthFlow is assembled at runtime and where each feature lives.

## High-Level Shape

```text
Browser
  |
  | HTML forms, AJAX fetch, JWT API calls
  v
Flask app factory: app/create_app()
  |
  | registers extensions, blueprints, security hooks, helpers
  v
Routes: app/routes/*
  |
  | call services, helpers, models
  v
Services: app/services/*
  |
  | business rules and side effects
  v
Models: app/models/__init__.py
  |
  | SQLAlchemy ORM
  v
SQLite locally, PostgreSQL-ready through DATABASE_URL
```

The frontend is server-rendered with Jinja templates. JavaScript is used for toasts, CSRF-aware fetch calls, form helpers, markdown/editor interactions, profile tabs, AJAX likes/stars/follows, and message polling.

## App Factory

`app/__init__.py` exposes `create_app(config_name=None)`.

Factory responsibilities:

- Load config from `config.py` using `APP_ENV`, `FLASK_ENV`, or `default`.
- Initialize SQLAlchemy, Flask-Login, and Flask-Migrate from `app/extensions.py`.
- Register blueprints for auth, main pages, blogs, projects, social, messages, admin, and API.
- Add session synchronization for logged-in users.
- Add manual CSRF protection for non-API write requests.
- Add security and cache headers.
- Add template globals such as `csrf_token()` and unread counts.
- Serve whitelisted upload folders from `/uploads/<folder>/<filename>`.
- Register the `flask init-db` CLI command.
- Ensure upload folders exist.
- Apply additive SQLite-only compatibility columns for older local databases.
- Configure rotating file logs under `logs/app.log`.

## Extensions

`app/extensions.py` creates extension singletons:

```text
db             Flask-SQLAlchemy
login_manager  Flask-Login
migrate        Flask-Migrate
```

They are initialized inside `init_extensions(app)` to keep imports safe and support app factories in tests.

## Configuration

`config.py` defines:

- `Config`: shared defaults and environment parsing.
- `DevelopmentConfig`: debug enabled.
- `TestingConfig`: CSRF disabled and in-memory SQLite by default.
- `ProductionConfig`: secure session and remember cookies enabled.

Important config behavior:

- `DATABASE_URL=postgres://...` is normalized to `postgresql://...`.
- Default database is `sqlite:///platform.db`.
- Relative `UPLOAD_FOLDER` values are resolved under the repository root.
- Allowed upload extensions are `png`, `jpg`, `jpeg`, `gif`, and `webp`.
- JWT expiration is controlled by `JWT_EXPIRATION_HOURS`.

## Blueprint Map

| Blueprint | File | Main Responsibility |
|---|---|---|
| `auth` | `app/routes/auth.py` | Register, verify signup, login, logout, password reset, OTP resend |
| `main` | `app/routes/main.py` | Dashboard, profiles, profile edit, settings, search, support, legal pages |
| `blog` | `app/routes/blog.py` | Blog feed, detail, create/edit/delete, comments, likes, bookmarks |
| `devlogs` | `app/routes/devlogs.py` | DevFeed, DevLog composer, feed pagination, likes, reposts, bookmarks, comments, media |
| `project` | `app/routes/project.py` | Project feed, detail, create/edit/delete, gallery images, stars |
| `social` | `app/routes/social.py` | Notifications, followers/following pages, follow/unfollow, pulse counts |
| `messages` | `app/routes/messages.py` | Inbox, chat, AJAX send, message polling |
| `admin` | `app/routes/admin.py` | Admin dashboard, suspension, reports, draft review |
| `api` | `app/routes/api.py` | JWT login, current user, public profiles/blogs/projects |

## Route Layer Pattern

Most route handlers follow this pattern:

1. Read request data from query args, form fields, JSON, or files.
2. Load the required SQLAlchemy model records.
3. Apply permission checks with `login_required`, `admin_required`, or `owner_required`.
4. Call a service or helper for shared behavior.
5. Commit database changes.
6. Return a template, redirect, or JSON response.

Route handlers currently contain some business logic directly. The cleanest future path is to keep validation and orchestration in routes, then move reusable rules into `app/services/`.

## Service Layer

### Auth Service

`app/services/auth.py` owns:

- Email normalization.
- 6-digit OTP generation.
- Password strength checks.
- User registration.
- OTP issuing and verification.
- Login authentication and lockout updates.
- Password reset start and completion.

OTP records are stored in `otp_tokens`. New OTPs consume older unconsumed tokens for the same user and purpose.

### Content Service

`app/services/content.py` owns:

- Slug generation with collision suffixes.
- Reading time calculation.
- Markdown rendering with fenced code, tables, and code highlighting.
- HTML sanitization through Bleach.
- Tag synchronization from comma-separated input.

### Gamification Service

`app/services/gamification.py` owns:

- XP reward values.
- Level formula.
- XP progress payloads.
- Daily bucket caps for selected actions.
- Source-level duplicate protection.
- Profile completion XP awards.

`award_xp(user, action, source=None)` is the main entry point.

### DevLog Service

`app/services/devlogs.py` owns:

- Hashtag extraction from DevLog text.
- Tag normalization and synchronization.
- Feed query ordering for latest, trending, following, and milestones.
- Viewer state batching for liked/bookmarked/reposted UI state.

### Notification Service

`app/services/notifications.py` owns:

- `Notification` record creation.
- Optional email notification dispatch.
- User preference checks for message, comment, follow, and like emails.

There is also `app/utils/helpers.py`, which imports and re-exports `create_notification` for older route code.

## Utility Layer

| File | Responsibility |
|---|---|
| `app/utils/uploads.py` | Validate, name, save, verify, resize, and delete uploaded images |
| `app/utils/decorators.py` | Custom login/admin/owner decorators |
| `app/utils/rate_limit.py` | Process-local fixed-window-ish rate limiting |
| `app/utils/email.py` | HTML email sender with async SMTP thread and mock logging |
| `app/utils/emailer.py` | Plain-text OTP and welcome email helpers |
| `app/utils/helpers.py` | Pagination, relative datetime formatting, compatibility imports |

## Request Lifecycle

### Web Form POST

```text
Browser submits POST form
  |
base.html injects _csrf_token if missing
  |
csrf_protect() checks session token
  |
route validates data and permissions
  |
models/services update database
  |
flash message and redirect
```

### AJAX Write

```text
Browser calls fetch()
  |
base.html wraps fetch and adds X-CSRFToken for non-GET requests
  |
csrf_protect() validates token unless path starts with /api/
  |
route returns JSON
```

### JWT API

```text
Client POSTs /api/login with email/password
  |
authenticate_user()
  |
JWT signed with SECRET_KEY and expiration
  |
Client sends Authorization: Bearer <token>
  |
/api/user or /api/me/xp decodes token manually
```

## Upload Pipeline

1. User uploads media through profile, blog, project, or DevLog forms.
2. Route calls `save_upload(file, folder, max_size=...)`.
3. Folder is checked against `avatars`, `banners`, `blogs`, `projects`, or `devlogs`.
4. Extension is checked against allowed image extensions. DevLog media also allows configured short-form video extensions.
5. A random hex prefix and secure filename are generated.
6. File is saved under `UPLOAD_FOLDER/<folder>/`.
7. Pillow verifies images.
8. Images are resized if larger than the configured max size.
9. The generated filename is stored in the database.

Default image names are protected from deletion:

```text
default.jpg
default_banner.jpg
```

## Notification Flow

```text
User action
  |
route calls create_notification()
  |
notifications table row is created
  |
optional email is sent based on preferences
  |
navbar badges read unread counts from context processor or /api/pulse
```

Notification actions currently used include:

```text
message
comment
follow
like
star
repost
system
```

## XP Flow

```text
Qualifying event
  |
route calls award_xp()
  |
XPTransaction is inserted
  |
database uniqueness prevents duplicate source or daily bucket awards
  |
users.xp_total and users.level are updated
  |
profile/dashboard reads current_user.xp_progress
```

Daily-capped actions:

```text
daily_login
daily_devlog
```

Source-capped actions use source type and source id. Examples: a specific blog publish, a specific like, a specific follow, or a specific project star.

## Frontend Architecture

Global frontend setup lives in `app/templates/base.html` and `app/static/js/main.js`.

Important frontend files:

| File | Responsibility |
|---|---|
| `main.js` | Toasts, local time formatting, form validation, password strength, button loaders |
| `auth.js` | Auth form interactions and OTP input behavior |
| `dashboard.js` | Sidebar/menu behavior, active navigation, admin table search, stat animation |
| `blog.js` | Like and bookmark AJAX helpers |
| `profile.js` | Follow button, profile tabs, copy profile link |
| `feed.js` | Feed filter interactions |
| `editor.js` | Reusable markdown editor draft/preview helper |
| `components.js` | Dropdowns, modals, tooltips |

Some templates also contain page-specific inline scripts, especially chat, support QR generation, tag suggestions, and blog upload autosave.

## Runtime Data

These directories are runtime/local and should not be committed:

```text
venv/
__pycache__/
.pytest_cache/
logs/
uploads/
instance/
*.db
```

`.gitignore` already excludes them.

## Current Architecture Tradeoffs

- All models live in one file. This makes relationships easy to inspect, but the file will become heavy as the product grows.
- The local development entry point calls `db.create_all()`. This is convenient locally, but production should rely on migrations.
- The rate limiter is in memory. It does not coordinate across multiple worker processes.
- JWT auth is simple and stateless. There is no token revocation table.
- Uploads are local files. Production deployments need persistent storage or object storage.
