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

Tokens are stored in the session and exposed to templates through `csrf_token()`. `base.html` injects missing hidden CSRF inputs into POST forms and adds `X-CSRFToken` to non-GET fetch calls.

### Rate Limiting

The in-memory limiter protects selected routes:

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
| `messages` | Direct messages |
| `follow` | Follow/unfollow |

Important: this limiter is process-local. Use Redis or another shared store before running multiple workers or servers.

### Upload Safety

Upload protections:

- Folder allowlist: `avatars`, `banners`, `blogs`, `projects`, `devlogs`.
- Extension allowlist: `png`, `jpg`, `jpeg`, `gif`, `webp`.
- DevLog video extension allowlist: `mp4`, `webm`, `mov`.
- Random hex filename prefix.
- `secure_filename()` for original filename portion.
- Pillow image verification.
- Resize and optimization.
- Failed upload cleanup.
- Upload route only serves allowed folders.

### HTML And Markdown Safety

Blog markdown is rendered in `app/services/content.py` and sanitized through Bleach.

Allowed HTML is limited to selected formatting, code, table, image, link, span, and div tags. Unsupported tags are stripped.

Jinja autoescaping protects templates by default.

### Security Headers

Configured headers:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Cache behavior:

- Static files are public cached for 7 days.
- Uploaded files are public cached for 1 day.
- API responses are `no-store`.
- Authenticated GET pages are `no-store`.
- Public anonymous GET pages are public cached for 120 seconds.

## Production Checklist

Before deploying:

- Set `APP_ENV=production`.
- Set a long random `SECRET_KEY`.
- Use PostgreSQL through `DATABASE_URL`.
- Configure SMTP credentials.
- Set `MAIL_DEFAULT_SENDER`.
- Use persistent upload storage.
- Run `flask db upgrade`.
- Run tests.
- Serve behind HTTPS.
- Use secure cookies, which `ProductionConfig` enables.
- Configure reverse proxy headers if needed.
- Rotate default seed passwords.
- Disable or protect demo accounts.
- Set up backups for database and uploads.
- Set up log collection and monitoring.
- Use a shared rate-limit backend if running more than one worker.

## Deployment Example

PowerShell setup:

```powershell
$env:APP_ENV='production'
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db upgrade
.\venv\Scripts\python.exe -m pytest -q
```

Gunicorn command:

```powershell
.\venv\Scripts\gunicorn.exe -w 4 -b 0.0.0.0:5000 run:app
```

On Windows, Gunicorn is not the normal production choice. Use a Linux host/container for Gunicorn, or choose a Windows-compatible WSGI server if deploying directly on Windows.

## Database Operations

### Local Development

`run.py` does:

1. Create the app.
2. Run `db.create_all()`.
3. Seed demo data if the SQLite database file is new.
4. Start Flask dev server.

This is convenient for local use but should not replace migrations in production.

### Production

Use migrations:

```powershell
$env:FLASK_APP='run.py'
.\venv\Scripts\flask.exe db upgrade
```

Backups:

- Back up the main database.
- Back up uploaded media.
- Back up `.env` separately and securely.
- Test restore regularly.

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

Production recommendations:

- Use persistent disk or object storage.
- Store only filenames or object keys in the database.
- Put upload serving behind a CDN if traffic grows.
- Set size limits at the reverse proxy and Flask level.
- Scan uploads if threat model requires it.

## Admin Operations

Admin dashboard:

```text
/admin/
```

Admin capabilities:

- View users and counts.
- Suspend/restore non-admin users.
- Update report status.
- Publish/unpublish draft blogs and projects.

Limitations:

- No audit log for admin actions yet.
- Admin suspension cannot suspend admin accounts from the panel.
- Report workflow is status-only.

## JWT Operations

JWTs:

- Are signed with `SECRET_KEY`.
- Expire after `JWT_EXPIRATION_HOURS`.
- Are checked manually in `/api/user` and `/api/me/xp`.

Operational limitations:

- No token revocation table.
- Rotating `SECRET_KEY` invalidates all tokens and Flask sessions.
- JWT API coverage is small and mostly read-only.

## Known Risks And Hardening Ideas

High value improvements:

- Add Redis-backed rate limiting.
- Add API rate limits, especially `/api/login`.
- Add pagination parameters to public API lists.
- Add an admin audit log.
- Add content moderation records for actions taken.
- Add account deletion and data export workflow beyond the current JSON export.
- Move uploads to object storage.
- Add server-side message pagination.
- Add SocketIO or server-sent events for realtime messaging/notifications.
- Add Content-Security-Policy after reviewing inline scripts.
- Add token revocation or short-lived access tokens plus refresh tokens for API auth.
- Add tests for blocked-user behavior and message permissions.

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
