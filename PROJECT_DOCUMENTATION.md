# AuthFlow Complete Project Documentation

Last updated: May 10, 2026

AuthFlow is a Flask developer community platform. It supports verified accounts, profiles, blogs, projects, DevLogs, follows, notifications, direct messages, moderation, uploads, a public/JWT API, and XP-based gamification.

This document is the top-level project guide. For deeper reference, see:

- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API_REFERENCE.md)
- [Database Schema](docs/DATABASE_SCHEMA.md)
- [Development Guide](docs/DEVELOPMENT_GUIDE.md)
- [Security And Operations](docs/SECURITY_AND_OPERATIONS.md)

## Executive Summary

AuthFlow is built as a server-rendered Flask app:

```text
Flask 3
SQLAlchemy 3
Flask-Login
Flask-Migrate / Alembic
Jinja2 templates
Vanilla JavaScript
SQLite locally, PostgreSQL-ready in production
```

The app uses an application factory, feature-specific blueprints, centralized SQLAlchemy models, services for shared business rules, and utilities for uploads, email, decorators, pagination, and rate limiting.

## Quick Start

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

Run seed data manually:

```powershell
.\venv\Scripts\python.exe populate_data.py
```

## Repository Layout

```text
.
|-- app/
|   |-- __init__.py
|   |-- extensions.py
|   |-- models/
|   |-- routes/
|   |-- services/
|   |-- utils/
|   |-- static/
|   |-- templates/
|-- docs/
|-- migrations/
|-- tests/
|-- uploads/
|-- instance/
|-- logs/
|-- config.py
|-- populate_data.py
|-- requirements.txt
|-- run.py
|-- README.md
`-- PROJECT_DOCUMENTATION.md
```

Runtime folders such as `uploads/`, `instance/`, `logs/`, caches, virtualenvs, and local databases are ignored by git.

## Runtime Entry Points

### `run.py`

Development entry point:

- Creates the app.
- Checks/creates database tables.
- Seeds local demo data if the SQLite database is new.
- Starts Flask with configured host and port.

### `app/__init__.py`

Application factory and runtime wiring:

- Loads config.
- Initializes extensions.
- Registers blueprints.
- Adds CSRF checks.
- Adds security/cache headers.
- Adds template globals and filters.
- Serves upload files.
- Registers CLI commands.
- Creates upload directories.
- Adds SQLite compatibility columns for older local DBs.
- Configures rotating logs.

### `config.py`

Environment-driven configuration:

- `DevelopmentConfig`
- `TestingConfig`
- `ProductionConfig`

Important settings include database URL, upload folder, upload limits, session/remember durations, mail server, lockout limits, pagination, JWT expiration, and security headers.

## Feature Guide

### Authentication

Files:

```text
app/routes/auth.py
app/services/auth.py
app/models/__init__.py  # User, OTPToken
app/utils/emailer.py
```

Capabilities:

- Register with username, email, and strong password.
- Issue email verification OTP.
- Verify signup OTP.
- Resend signup or reset OTP.
- Log in with email/password.
- Block login until email is verified.
- Lock accounts after repeated failed login attempts.
- Remember users with Flask-Login.
- Start password reset by email.
- Verify password reset OTP.
- Set new password.

Password rules:

```text
at least 10 characters
lowercase letter
uppercase letter
number
symbol
```

### Profiles

Files:

```text
app/routes/main.py
app/templates/profile/
app/static/js/profile.js
```

Capabilities:

- Public profile at `/<username>`.
- Edit profile at `/profile/edit`.
- Avatar and banner uploads.
- Full name, headline, bio, location, website, resume link.
- Skills and social links.
- Featured blog and featured project.
- Profile completion score and tips.
- Profile views counter.
- Followers and following counts.
- Follow/unfollow button.
- Report and block actions.
- Account data export from settings.

Profile completion currently checks 11 items and awards XP once the profile reaches at least 90 percent.

### Blogs

Files:

```text
app/routes/blog.py
app/services/content.py
app/templates/content/
app/templates/feed/
app/static/js/blog.js
```

Capabilities:

- Blog feed at `/blogs`.
- Filters by category, tag, query, and sort.
- Detail page at `/blog/<slug>`.
- Create at `/upload/blog`.
- Edit/delete owned blogs.
- Draft and published status.
- Markdown content with sanitized HTML output.
- Reading time calculation.
- Thumbnail upload.
- Tags and categories.
- Comments.
- Likes.
- Bookmarks.
- Related posts.
- Recently viewed blogs stored in session.

### Projects

Files:

```text
app/routes/project.py
app/templates/content/upload_project.html
app/templates/content/project_detail.html
app/templates/feed/projects_feed.html
```

Capabilities:

- Project feed at `/projects`.
- Filters by category, tag, and sort.
- Detail page at `/project/<slug>`.
- Create at `/upload/project`.
- Edit/delete owned projects.
- Draft and published status.
- Thumbnail upload.
- Gallery image upload and delete.
- Tags as tech stack.
- GitHub and demo URLs.
- Star/unstar action.
- Related projects.

### DevLogs And DevFeed

Files:

```text
app/routes/devlogs.py
app/services/devlogs.py
app/templates/devlogs/
app/static/js/devlogs.js
app/static/css/devlogs.css
```

Capabilities:

- DevFeed at `/devfeed` and `/devlogs`.
- DevLog detail at `/devlogs/<id>`.
- AJAX composer with text, progress, milestone, hashtags, image/video media.
- Infinite loading with `?ajax=1`.
- Sorts for latest, trending, following, and milestones.
- Hashtag extraction and tag synchronization.
- Like, repost, bookmark, comment, and pin actions.
- Optimistic-style UI updates backed by database writes.
- Notifications for likes, reposts, and comments.
- Daily DevLog XP through the existing `daily_devlog` reward.
- Homepage dashboard integration through a live DevLogs panel.

### Social Layer

Files:

```text
app/routes/social.py
app/services/notifications.py
app/models/__init__.py  # Follow, Notification
```

Capabilities:

- Follow/unfollow users.
- Followers page.
- Following page.
- Following feed.
- Notification list.
- Clear notifications.
- Unread notification count.
- Lightweight pulse endpoint for notification/message badges.

### Messages

Files:

```text
app/routes/messages.py
app/templates/messages/
```

Capabilities:

- Inbox at `/messages`.
- Chat at `/messages/<username>`.
- AJAX send through `/messages/send`.
- AJAX polling with `last_id`.
- Read/unread state.
- Conversation list sorted by last message.
- Block checks.
- Message permission checks: everyone, followers, none.
- Notification when a message is sent.

### Admin

Files:

```text
app/routes/admin.py
app/templates/dashboard/admin.html
app/utils/decorators.py
```

Capabilities:

- Admin dashboard.
- User suspension/restoration for non-admin accounts.
- Report status updates.
- Blog draft publish/unpublish.
- Project draft publish/unpublish.
- Summary counts for users, admins, blogs, projects, and open reports.

### Support And Legal

Files:

```text
app/routes/main.py
app/templates/legal/
app/static/css/support.css
```

Capabilities:

- Privacy page.
- Terms page.
- Support page.
- UPI QR generation endpoint for selected/custom amounts.
- Interactive FAQ/help center at `/faq`.

### Gamification

Files:

```text
app/services/gamification.py
app/models/__init__.py  # XPTransaction
```

Reward table:

| Action | XP |
|---|---:|
| `daily_login` | 10 |
| `publish_blog` | 50 |
| `receive_blog_like` | 8 |
| `publish_project` | 60 |
| `receive_project_star` | 10 |
| `comment` | 12 |
| `receive_follow` | 15 |
| `complete_profile` | 100 |
| `daily_devlog` | 20 |

Daily-capped actions:

```text
daily_login
daily_devlog
```

Level formula:

```text
cumulative_xp_for_level = floor(100 * (level - 1) ^ 1.6)
```

`users.xp_total` and `users.level` are denormalized for fast rendering. `xp_transactions` is the audit trail and duplicate-protection mechanism.

## Route Catalogue

Route map generated from the Flask app:

| Methods | Path | Endpoint |
|---|---|---|
| GET | `/` | `main.home` |
| GET | `/<username>` | `main.public_profile` |
| GET | `/<username>/followers` | `social.followers` |
| GET | `/<username>/following` | `social.following` |
| GET | `/admin/` | `admin.admin_dashboard` |
| POST | `/admin/content/blogs/<int:blog_id>/status` | `admin.update_blog_status` |
| POST | `/admin/content/projects/<int:project_id>/status` | `admin.update_project_status` |
| GET | `/admin/login` | `admin.admin_login` |
| POST | `/admin/reports/<int:report_id>/status` | `admin.update_report_status` |
| POST | `/admin/users/<int:user_id>/toggle-active` | `admin.toggle_user_active` |
| GET | `/api/blogs` | `api.api_blogs` |
| GET | `/api/blogs/<slug>` | `api.api_blog` |
| POST | `/api/generate-qr` | `main.generate_qr` |
| POST | `/api/login` | `api.api_login` |
| GET | `/api/me/xp` | `api.api_my_xp` |
| GET | `/api/notifications/count` | `social.get_notifications_count` |
| GET | `/api/profiles` | `api.api_profiles` |
| GET | `/api/profiles/<username>` | `api.api_profile` |
| GET | `/api/projects` | `api.api_projects` |
| GET | `/api/projects/<slug>` | `api.api_project` |
| GET | `/api/pulse` | `social.get_activity_pulse` |
| GET | `/api/user` | `api.api_user` |
| POST | `/block/<username>` | `main.block_user` |
| POST | `/blog/<int:blog_id>/bookmark` | `blog.bookmark_blog` |
| POST | `/blog/<int:blog_id>/comment` | `blog.add_comment` |
| POST | `/blog/<int:blog_id>/delete` | `blog.delete_blog` |
| GET, POST | `/blog/<int:blog_id>/edit` | `blog.edit_blog` |
| POST | `/blog/<int:blog_id>/like` | `blog.like_blog` |
| GET | `/blog/<slug>` | `blog.blog_detail` |
| GET | `/blogs` | `blog.blogs_feed` |
| GET | `/bookmarks` | `main.bookmarks` |
| GET | `/devfeed` | `devlogs.index` |
| GET | `/devlogs` | `devlogs.index` |
| POST | `/devlogs` | `devlogs.create` |
| GET | `/devlogs/<int:devlog_id>` | `devlogs.detail` |
| POST | `/devlogs/<int:devlog_id>/bookmark` | `devlogs.bookmark` |
| POST | `/devlogs/<int:devlog_id>/comments` | `devlogs.comment` |
| POST | `/devlogs/<int:devlog_id>/like` | `devlogs.like` |
| POST | `/devlogs/<int:devlog_id>/pin` | `devlogs.pin` |
| POST | `/devlogs/<int:devlog_id>/repost` | `devlogs.repost` |
| POST | `/devlogs/media/<int:media_id>/delete` | `devlogs.delete_media` |
| GET | `/faq` | `main.faq` |
| POST | `/follow/<username>` | `social.follow_user` |
| GET | `/following` | `main.following_feed` |
| GET, POST | `/forgot` | `auth.forgot_password` |
| GET, POST | `/login` | `auth.login` |
| GET | `/logout` | `auth.logout` |
| GET | `/messages` | `messages.inbox` |
| GET | `/messages/<username>` | `messages.chat` |
| POST | `/messages/send` | `messages.send_message` |
| GET, POST | `/new-password` | `auth.new_password` |
| GET | `/notifications` | `social.notifications` |
| POST | `/notifications/clear` | `social.clear_notifications` |
| GET | `/privacy` | `main.privacy` |
| GET, POST | `/profile/edit` | `main.edit_profile` |
| POST | `/project/<int:project_id>/delete` | `project.delete_project` |
| GET, POST | `/project/<int:project_id>/edit` | `project.edit_project` |
| POST | `/project/<int:project_id>/star` | `project.star_project` |
| GET | `/project/<slug>` | `project.project_detail` |
| POST | `/project/image/<int:image_id>/delete` | `project.delete_project_image` |
| GET | `/projects` | `project.projects_feed` |
| GET, POST | `/register` | `auth.register` |
| POST | `/report/<username>` | `main.report_user` |
| POST | `/resend-otp` | `auth.resend_otp` |
| POST | `/resend-verification` | `auth.resend_verification` |
| GET, POST | `/reset-verify` | `auth.reset_verify` |
| GET | `/search` | `main.search` |
| GET | `/settings` | `main.settings` |
| POST | `/settings/email` | `main.start_email_change` |
| POST | `/settings/email/verify` | `main.verify_email_change` |
| GET | `/settings/export` | `main.export_account_data` |
| POST | `/settings/logout-devices` | `main.logout_all_devices` |
| POST | `/settings/password` | `main.change_password` |
| POST | `/settings/preferences` | `main.update_preferences` |
| GET | `/support` | `main.support` |
| GET | `/tags/suggest` | `main.suggest_tags` |
| GET | `/terms` | `main.terms` |
| GET, POST | `/upload/blog` | `blog.create_blog` |
| GET, POST | `/upload/project` | `project.create_project` |
| GET | `/uploads/<folder>/<path:filename>` | `uploaded_file` |
| GET, POST | `/verify-signup` | `auth.verify_signup` |

## Data Model Summary

Primary tables:

```text
users
blogs
projects
comments
categories
tags
devlogs
devlog_media
devlog_comments
devlog_likes
devlog_bookmarks
devlog_reposts
follows
messages
notifications
otp_tokens
bookmarks
blog_likes
project_images
project_stars
xp_transactions
blocks
reports
```

Join tables:

```text
blog_tags
project_tags
devlog_tags
```

Important unique constraints:

```text
users.username
users.email
categories.name
categories.slug
tags.name
tags.slug
blogs.slug
projects.slug
devlog_likes(user_id, devlog_id)
devlog_bookmarks(user_id, devlog_id)
devlog_reposts(user_id, devlog_id)
follows(follower_id, followed_id)
blog_likes(user_id, blog_id)
bookmarks(user_id, blog_id)
project_stars(user_id, project_id)
blocks(blocker_id, blocked_id)
xp_transactions(user_id, action, source_type, source_id)
xp_transactions(user_id, action, bucket_key)
```

## Frontend Summary

Templates are grouped by feature:

```text
auth/
components/
content/
dashboard/
errors/
feed/
legal/
messages/
profile/
social/
email/
```

CSS files:

```text
style.css
animations.css
components.css
auth.css
dashboard.css
blog.css
feed.css
profile.css
support.css
```

JavaScript files:

```text
main.js
auth.js
dashboard.js
blog.js
profile.js
feed.js
editor.js
components.js
```

`base.html` provides the shared shell, CSRF token, toast container, cookie banner, notification sound, pulse polling, and fetch wrapper.

## Security Summary

Implemented controls:

- Password hashing.
- Email verification.
- OTP password reset.
- Login lockout.
- CSRF on web writes.
- Security headers.
- Upload folder allowlist.
- Upload extension allowlist.
- Image verification through Pillow.
- Markdown sanitization through Bleach.
- SQLAlchemy ORM query use.
- Route-level login/admin/owner checks.
- In-memory rate limiting on sensitive web actions.

Production requirements:

- Strong `SECRET_KEY`.
- HTTPS.
- Real SMTP credentials.
- PostgreSQL or another production database.
- Persistent upload storage.
- Migrations instead of relying on `db.create_all()`.
- Shared rate limiter if using multiple processes.
- Centralized logging and backups.

## Test Suite

Test file:

```text
tests/test_app_smoke.py
```

Covered behavior:

- Public page rendering.
- Cache headers.
- Remember-me login cookie.
- Bookmarks.
- Profile edit and featured fields.
- Public API and tag suggestions.
- OTP resend.
- Admin moderation.
- XP caps and level progress.
- Project star XP.
- DevLog feed rendering, creation, likes, bookmarks, reposts, and comments.

Run:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

## Maintenance Notes

High-value future work:

- Add Redis-backed rate limiting.
- Add API pagination and filtering.
- Add API rate limits, especially login.
- Add admin audit log.
- Add account deletion workflow.
- Add server-side autosave for blogs.
- Add full-text search.
- Add realtime messages/notifications through SocketIO or SSE.
- Move uploads to object storage for production.
- Add Content-Security-Policy after reducing inline scripts.
- Add more tests for blocking, message permissions, uploads, CSRF failures, and admin edge cases.

## Documentation Maintenance Checklist

When code changes, update docs if you change:

- Routes or endpoint behavior.
- Environment variables.
- Database models or migrations.
- Auth, CSRF, security, upload, or email behavior.
- Developer setup commands.
- API payload shape.
- Test expectations.
