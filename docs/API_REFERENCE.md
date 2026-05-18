# API Reference

AuthFlow has two kinds of JSON endpoints:

- `/api/*` endpoints for public content, JWT login, QR generation, live counts, and current-user data.
- Session-backed AJAX endpoints used by the Jinja frontend for likes, bookmarks, follows, messages, stars, and tag suggestions.

Web CSRF protection is skipped for paths beginning with `/api/`. Non-API write endpoints require the session CSRF token, usually added automatically by `base.html`.

## Authentication Types

### Public

No auth required.

### Session

Requires a normal Flask-Login browser session. Used by frontend AJAX and web pages.

### JWT

Requires:

```text
Authorization: Bearer <token>
```

Tokens are created by `POST /api/login`, signed with `SECRET_KEY`, and expire after `JWT_EXPIRATION_HOURS`.

## Public API Endpoints

### POST `/api/login`

Authenticates a verified user and returns a JWT.

Request:

```json
{
  "email": "demo@example.com",
  "password": "password"
}
```

Success:

```json
{
  "success": true,
  "token": "<jwt>",
  "user": {
    "username": "demo",
    "email": "demo@example.com"
  }
}
```

Failure:

```json
{
  "success": false,
  "message": "Invalid email or password."
}
```

Status: `401`

### GET `/api/profiles`

Returns up to 25 active users, newest first.

Response item:

```json
{
  "username": "demo",
  "full_name": "Demo Developer",
  "headline": "Full-stack developer building Flask and AI tools",
  "bio": "I build useful software products...",
  "skills": ["python", "flask", "javascript"],
  "followers_count": 3,
  "following_count": 4,
  "profile_views_count": 12,
  "xp_total": 120,
  "level": 2,
  "xp_progress": {
    "level": 2,
    "current": 20,
    "needed": 203,
    "percent": 10,
    "total": 120,
    "next_level_total": 303
  }
}
```

### GET `/api/profiles/<username>`

Returns one active user plus up to 10 published blogs and 10 published projects.

Extra fields:

```json
{
  "blogs": [
    {
      "title": "Hello",
      "slug": "hello",
      "excerpt": "Short summary",
      "reading_time": 1,
      "views_count": 5,
      "likes_count": 2,
      "author": "demo",
      "tags": ["flask"],
      "published_at": "2026-05-10T10:00:00"
    }
  ],
  "projects": [
    {
      "title": "Project",
      "slug": "project",
      "description": "A useful project",
      "github_url": "https://github.com/example/project",
      "demo_url": "https://example.com",
      "stars_count": 3,
      "author": "demo",
      "tech_stack": ["flask"],
      "created_at": "2026-05-10T10:00:00"
    }
  ]
}
```

### GET `/api/blogs`

Returns up to 25 published blogs, newest first.

Response item:

```json
{
  "title": "Hello",
  "slug": "hello",
  "excerpt": "Short summary",
  "reading_time": 1,
  "views_count": 5,
  "likes_count": 2,
  "author": "demo",
  "tags": ["flask"],
  "published_at": "2026-05-10T10:00:00"
}
```

### GET `/api/blogs/<slug>`

Returns one published blog. Adds raw markdown `content` to the blog payload.

```json
{
  "title": "Hello",
  "slug": "hello",
  "content": "Hello **world**"
}
```

### GET `/api/projects`

Returns up to 25 published projects, newest first.

Response item:

```json
{
  "title": "Project",
  "slug": "project",
  "description": "A useful project",
  "github_url": "https://github.com/example/project",
  "demo_url": "https://example.com",
  "stars_count": 3,
  "author": "demo",
  "tech_stack": ["python", "flask"],
  "created_at": "2026-05-10T10:00:00"
}
```

### GET `/api/projects/<slug>`

Returns one published project. Adds `gallery`.

```json
{
  "title": "Project",
  "slug": "project",
  "gallery": [
    {
      "filename": "abc123_screenshot.png",
      "caption": "Home screen"
    }
  ]
}
```

### POST `/api/generate-qr`

Generates a base64 PNG UPI QR code for the support page.

Request:

```json
{
  "amount": 99
}
```

Success:

```json
{
  "success": true,
  "qr_code": "<base64-png>",
  "upi_link": "upi://pay?...",
  "amount": 99.0
}
```

Errors:

```json
{
  "error": "Invalid amount"
}
```

Status: `400`

## JWT Endpoints

### GET `/api/user`

Requires JWT. Returns current user profile data plus email.

```json
{
  "username": "demo",
  "email": "demo@example.com",
  "full_name": "Demo Developer",
  "skills": ["python", "flask"],
  "xp_total": 120,
  "level": 2,
  "xp_progress": {
    "level": 2,
    "current": 20,
    "needed": 203,
    "percent": 10,
    "total": 120,
    "next_level_total": 303
  }
}
```

Invalid token:

```json
{
  "error": "Invalid token"
}
```

Status: `401`

### GET `/api/me/xp`

Requires JWT. Returns `current_user.xp_progress`.

```json
{
  "level": 2,
  "current": 20,
  "needed": 203,
  "percent": 10,
  "total": 120,
  "next_level_total": 303
}
```

## Session JSON Endpoints

These require a browser session and `login_required`.

### GET `/devlogs?ajax=1&page=2&sort=latest`

Returns rendered DevLog cards for infinite loading.

```json
{
  "html": "<article class=\"devlog-card\">...</article>",
  "has_next": true,
  "next_page": 3
}
```

Supported sorts:

```text
latest
trending
following
milestones
```

### POST `/devlogs`

Creates a DevLog. Requires session auth. Supports multipart form data.

Form fields:

```text
content=<required text, max 1200 stored>
progress=<0-100>
milestone=<optional text>
hashtags=<comma-separated optional tags>
media=<up to 4 image/video files>
```

AJAX success:

```json
{
  "status": "created",
  "html": "<article class=\"devlog-card\">...</article>",
  "id": 12
}
```

### POST `/devlogs/<devlog_id>/like`

Toggles a DevLog like.

```json
{
  "status": "liked",
  "count": 4
}
```

or:

```json
{
  "status": "unliked",
  "count": 3
}
```

### POST `/devlogs/<devlog_id>/bookmark`

Toggles a DevLog bookmark.

```json
{
  "status": "bookmarked",
  "count": 2
}
```

### POST `/devlogs/<devlog_id>/repost`

Toggles a DevLog repost. Users cannot repost their own DevLogs.

```json
{
  "status": "reposted",
  "count": 7
}
```

### POST `/devlogs/<devlog_id>/comments`

Creates a DevLog comment.

Form fields:

```text
content=<required comment text>
```

Success:

```json
{
  "status": "created",
  "html": "<div class=\"devlog-comment\">...</div>",
  "count": 1
}
```

### POST `/devlogs/<devlog_id>/pin`

Toggles pinned state. Only the DevLog owner or an admin may use it.

```json
{
  "status": "pinned",
  "is_pinned": true
}
```

### POST `/devlogs/media/<media_id>/delete`

Deletes a DevLog media attachment. Only the DevLog owner or an admin may use it.

```json
{
  "status": "deleted"
}
```

### GET `/api/notifications/count`

Returns unread notification count.

```json
{
  "count": 3
}
```

### GET `/api/pulse`

Returns lightweight unread counts for live badges.

```json
{
  "notifications": 3,
  "messages": 2
}
```

### GET `/tags/suggest?q=fla`

Returns up to 12 matching tags, sorted by name.

```json
[
  {
    "name": "flask",
    "slug": "flask"
  }
]
```

### GET `/settings/export`

Returns account data for the logged-in user.

```json
{
  "user": {
    "username": "demo",
    "email": "demo@example.com",
    "skills": ["python", "flask"],
    "created_at": "2026-05-10T10:00:00"
  },
  "blogs": [
    {
      "title": "Hello",
      "slug": "hello",
      "status": "published",
      "created_at": "2026-05-10T10:00:00"
    }
  ],
  "projects": [],
  "bookmarks": []
}
```

### POST `/follow/<username>`

Toggles follow state.

Success:

```json
{
  "status": "followed"
}
```

or:

```json
{
  "status": "unfollowed"
}
```

Self-follow error:

```json
{
  "error": "Cannot follow yourself"
}
```

Status: `400`

### POST `/blog/<blog_id>/like`

Toggles blog like.

```json
{
  "status": "liked",
  "count": 12
}
```

or:

```json
{
  "status": "unliked",
  "count": 11
}
```

### POST `/blog/<blog_id>/bookmark`

Toggles bookmark.

```json
{
  "status": "bookmarked"
}
```

or:

```json
{
  "status": "unbookmarked"
}
```

### POST `/project/<project_id>/star`

Toggles project star.

```json
{
  "status": "starred",
  "count": 4
}
```

or:

```json
{
  "status": "unstarred",
  "count": 3
}
```

### POST `/messages/send`

Sends a direct message.

Form fields:

```text
recipient_id=<int>
content=<message text>
```

AJAX success:

```json
{
  "status": "sent",
  "message": {
    "id": 42,
    "content": "Hello",
    "sender_id": 1,
    "is_read": false,
    "created_at": "2026-05-10T10:00:00Z"
  }
}
```

Possible errors:

```json
{"error": "Invalid data"}
{"error": "Cannot message yourself"}
{"error": "This user is not available for messages"}
{"error": "This user is not accepting messages"}
{"error": "Only followers can message this user"}
```

### GET `/messages/<username>?last_id=<id>&ajax=1`

Returns messages in the conversation, optionally only messages with id greater than `last_id`.

```json
{
  "messages": [
    {
      "id": 42,
      "content": "Hello",
      "sender_id": 1,
      "is_read": false,
      "created_at": "2026-05-10T10:00:00Z"
    }
  ]
}
```

### POST `/notifications/clear`

Deletes all notifications for the current user.

```json
{
  "status": "cleared"
}
```

## Non-JSON Web POST Routes

These mutate data and redirect with flash messages:

```text
POST /register
POST /verify-signup
POST /resend-verification
POST /resend-otp
POST /login
POST /forgot
POST /reset-verify
POST /new-password
POST /upload/blog
POST /blog/<blog_id>/edit
POST /blog/<blog_id>/delete
POST /blog/<blog_id>/comment
POST /upload/project
POST /project/<project_id>/edit
POST /project/image/<image_id>/delete
POST /project/<project_id>/delete
POST /settings/preferences
POST /settings/password
POST /settings/email
POST /settings/email/verify
POST /settings/logout-devices
POST /report/<username>
POST /block/<username>
POST /admin/users/<user_id>/toggle-active
POST /admin/reports/<report_id>/status
POST /admin/content/blogs/<blog_id>/status
POST /admin/content/projects/<project_id>/status
```

## Error Behavior

- Missing records usually return Flask's `404`.
- Invalid JWT returns `401`.
- Failed API login returns `401`.
- Rate limit violations return `429`.
- Invalid CSRF returns `400`.
- Non-admin admin access returns `403` or redirects to login.

## Current API Limitations

- Public list endpoints are fixed at 25 records and do not expose pagination controls.
- JWT tokens are not revocable except by rotating `SECRET_KEY`.
- `/api/login` has no dedicated API rate limiter decorator at the route level.
- Public API responses are intentionally compact and do not include every database field.
