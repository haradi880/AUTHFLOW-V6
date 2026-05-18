# Database Schema

AuthFlow uses SQLAlchemy models in `app/models/__init__.py`. This document summarizes the schema and relationships as implemented in code.

## Model Overview

```text
User
  |-- Blog
  |     |-- Comment
  |     |-- BlogLike
  |     |-- Bookmark
  |     |-- Tag through blog_tags
  |
  |-- Project
  |     |-- ProjectImage
  |     |-- ProjectStar
  |     |-- Tag through project_tags
  |
  |-- DevLog
  |     |-- DevLogMedia
  |     |-- DevLogComment
  |     |-- DevLogLike
  |     |-- DevLogBookmark
  |     |-- DevLogRepost
  |     |-- Tag through devlog_tags
  |
  |-- Follow as follower/followed
  |-- Message as sender/recipient
  |-- Notification as recipient/from_user
  |-- OTPToken
  |-- XPTransaction
  |-- Block as blocker/blocked
  |-- Report as reporter/reported_user

Category
  |-- Blog
  |-- Project
```

## Tables

### `users`

Core account, profile, preference, and XP table.

Important columns:

| Column | Notes |
|---|---|
| `id` | Primary key |
| `username` | Unique, indexed, public profile slug |
| `email` | Unique, indexed, normalized to lowercase by auth service |
| `password_hash` | Werkzeug password hash |
| `full_name`, `headline`, `bio`, `location`, `website`, `resume_url` | Profile fields |
| `avatar`, `banner` | Upload filenames, default to `default.jpg` and `default_banner.jpg` |
| `skills` | Comma-separated string, exposed as a list through `get_skills_list()` |
| `twitter`, `linkedin`, `github` | Social/profile links |
| `is_admin` | Admin access flag |
| `is_verified` | Email verification flag |
| `is_active` | Database column backing model attribute `active` and property `is_active` |
| `failed_login_count`, `locked_until` | Login lockout tracking |
| `featured_blog_id`, `featured_project_id` | Optional featured profile content |
| `pending_email` | Email change flow |
| `email_on_messages`, `email_on_comments`, `email_on_follows`, `email_on_likes`, `weekly_digest` | Notification preferences |
| `message_permission` | `everyone`, `followers`, or `none` |
| `profile_views_count` | Public profile view counter |
| `xp_total`, `level`, `profile_xp_awarded_at` | Gamification state |
| `created_at`, `updated_at` | From `TimestampMixin` |

Useful methods/properties:

- `set_password(password)`
- `check_password(password)`
- `is_locked()`
- `register_failed_login()`
- `clear_failed_logins()`
- `profile_completion()`
- `xp_progress`
- `follow(user)`, `unfollow(user)`, `is_following(user)`
- `followers_count()`, `following_count()`
- `avatar_url`, `banner_url`

### `follows`

Social graph join table.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `follower_id` | User who follows |
| `followed_id` | User being followed |
| `created_at` | Timestamp |

Constraint:

```text
Unique: follower_id, followed_id
```

### `xp_transactions`

Immutable-ish audit trail for XP awards.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `user_id` | Award recipient |
| `action` | Reward action name |
| `points` | Points awarded |
| `source_type`, `source_id` | Source object identity for once-per-source rewards |
| `meta` | JSON metadata |
| `awarded_at` | Timestamp |
| `bucket_key` | Daily bucket for daily-capped actions |

Constraints:

```text
Unique: user_id, action, source_type, source_id
Unique: user_id, action, bucket_key
```

These constraints are how `award_xp()` prevents duplicate farming.

### `categories`

Shared content category table.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `name` | Unique display name |
| `slug` | Unique indexed URL/filter slug |
| `description` | Optional description |

Relationships:

- One category has many blogs.
- One category has many projects.

### `tags`

Shared tag table for blogs and projects.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `name` | Unique tag name |
| `slug` | Unique indexed slug |

Relationships are many-to-many through `blog_tags` and `project_tags`.

### `blog_tags`

Many-to-many join table.

```text
blog_id -> blogs.id
tag_id  -> tags.id
```

Composite primary key:

```text
blog_id, tag_id
```

### `project_tags`

Many-to-many join table.

```text
project_id -> projects.id
tag_id     -> tags.id
```

Composite primary key:

```text
project_id, tag_id
```

### `blogs`

Blog content table.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `title` | Required title |
| `slug` | Unique indexed slug |
| `content` | Required markdown source |
| `excerpt` | Short summary |
| `thumbnail` | Upload filename |
| `status` | `draft` or `published` |
| `reading_time` | Calculated minutes |
| `views_count`, `likes_count`, `comments_count` | Denormalized counters |
| `published_at` | First publish timestamp |
| `user_id` | Author |
| `category_id` | Optional category |
| `created_at`, `updated_at` | From `TimestampMixin` |

Relationships:

- Author: `User`
- Category: `Category`
- Tags: many-to-many `Tag`
- Comments: one-to-many `Comment`
- Likes: one-to-many `BlogLike`
- Bookmarks: one-to-many `Bookmark`

### `projects`

Project showcase table.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `title` | Required title |
| `slug` | Unique indexed slug |
| `description` | Required text |
| `thumbnail` | Upload filename |
| `github_url`, `demo_url` | Optional links |
| `stars_count` | Denormalized star counter |
| `status` | `draft` or `published` |
| `user_id` | Author |
| `category_id` | Optional category |
| `created_at`, `updated_at` | From `TimestampMixin` |

Relationships:

- Author: `User`
- Category: `Category`
- Tags: many-to-many `Tag`
- Images: one-to-many `ProjectImage`
- Stars: one-to-many `ProjectStar`

### `project_stars`

Project star join table.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `user_id` | User who starred |
| `project_id` | Starred project |
| `created_at` | Timestamp |

Constraint:

```text
Unique: user_id, project_id
```

### `project_images`

Gallery images for projects.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `filename` | Upload filename |
| `caption` | Optional caption |
| `order` | Sort order |
| `project_id` | Parent project |

Property:

- `url`: upload route URL for the file.

### `devlogs`

Build-in-public updates and activity feed items.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `content` | Required update text |
| `progress` | 0-100 build progress |
| `milestone` | Optional short milestone |
| `is_pinned` | Owner/admin pinned state |
| `visibility` | Currently `public` |
| `likes_count`, `comments_count`, `reposts_count`, `bookmarks_count` | Denormalized counters |
| `user_id` | Author |
| `created_at`, `updated_at` | From `TimestampMixin` |

Relationships:

- Author: `User`
- Tags: many-to-many `Tag`
- Media: one-to-many `DevLogMedia`
- Comments: one-to-many `DevLogComment`
- Likes: one-to-many `DevLogLike`
- Bookmarks: one-to-many `DevLogBookmark`
- Reposts: one-to-many `DevLogRepost`

### `devlog_tags`

Many-to-many join table.

```text
devlog_id -> devlogs.id
tag_id    -> tags.id
```

### `devlog_media`

Media attachments for DevLogs.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `filename` | Upload filename |
| `media_type` | `image` or `video` |
| `alt_text` | Optional alt text |
| `order` | Sort order |
| `devlog_id` | Parent DevLog |

### `devlog_comments`

Threaded discussion layer for DevLogs.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `content` | Required text |
| `user_id` | Author |
| `devlog_id` | Parent DevLog |
| `created_at`, `updated_at` | From `TimestampMixin` |

### `devlog_likes`

Unique user likes for DevLogs.

Constraint:

```text
Unique: user_id, devlog_id
```

### `devlog_bookmarks`

Unique user saves for DevLogs.

Constraint:

```text
Unique: user_id, devlog_id
```

### `devlog_reposts`

Unique user reposts for DevLogs.

Constraint:

```text
Unique: user_id, devlog_id
```

### `comments`

Blog comments and replies.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `content` | Required text |
| `parent_id` | Optional parent comment |
| `user_id` | Author |
| `blog_id` | Parent blog |
| `created_at`, `updated_at` | From `TimestampMixin` |

Current route support creates top-level comments only. The model already supports replies.

### `blog_likes`

Blog like join table.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `user_id` | User who liked |
| `blog_id` | Liked blog |
| `created_at` | Timestamp |

Constraint:

```text
Unique: user_id, blog_id
```

### `bookmarks`

User-saved blogs.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `user_id` | Bookmark owner |
| `blog_id` | Saved blog |
| `created_at` | Timestamp |

Constraint:

```text
Unique: user_id, blog_id
```

### `notifications`

User notification table.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `user_id` | Recipient |
| `action` | Notification category |
| `message` | Display message |
| `link` | Optional target URL |
| `is_read` | Unread/read state |
| `from_user_id` | Optional actor |
| `created_at` | Timestamp |

### `otp_tokens`

Email verification, password reset, and email change tokens.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `user_id` | Token owner |
| `purpose` | `email_verification`, `password_reset`, or `email_change` |
| `code_hash` | Hashed OTP code |
| `expires_at` | Expiration time |
| `consumed_at` | Null until used or invalidated |
| `created_at` | Timestamp |

Only the latest unconsumed token for a purpose is considered valid.

### `messages`

Direct messages.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `sender_id` | Sender user |
| `recipient_id` | Recipient user |
| `content` | Message body |
| `is_read` | Read state |
| `created_at` | Timestamp |

### `blocks`

User block relationships.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `blocker_id` | User who blocked |
| `blocked_id` | User being blocked |
| `created_at` | Timestamp |

Constraint:

```text
Unique: blocker_id, blocked_id
```

Current behavior prevents blocked users from messaging the blocker.

### `reports`

Moderation reports.

| Column | Notes |
|---|---|
| `id` | Primary key |
| `reporter_id` | Reporter, nullable if reporter deleted |
| `reported_user_id` | Reported user |
| `reason` | Short reason |
| `details` | Optional details, capped by route |
| `status` | `open`, `reviewing`, `resolved`, or `dismissed` |
| `created_at` | Timestamp |

## Cascades

Common cascade behavior:

- Deleting a user cascades authored blogs, projects, comments, OTP tokens, notifications, XP transactions, follows, blocks, messages through FK cascade/backref behavior.
- Deleting a blog cascades comments, likes, bookmarks, and blog-tag joins.
- Deleting a project cascades project images, stars, and project-tag joins.
- Deleting a category sets related `category_id` values to null.
- Featured blog/project references are set to null on content deletion.

## Denormalized Counters

The app stores some counters for faster rendering:

```text
blogs.views_count
blogs.likes_count
blogs.comments_count
projects.stars_count
devlogs.likes_count
devlogs.comments_count
devlogs.reposts_count
devlogs.bookmarks_count
users.profile_views_count
users.xp_total
users.level
```

When adding new features, keep counter updates in the same transaction as the row insert/delete that caused the count change.

## Migrations

Flask-Migrate/Alembic is configured under `migrations/`.

Current revision:

```text
20260510_0002_add_devlogs.py
```

Recent migrations add:

- `users.xp_total`
- `users.level`
- `users.profile_xp_awarded_at`
- `xp_transactions`
- `project_stars`
- `devlogs`
- `devlog_media`
- `devlog_comments`
- `devlog_likes`
- `devlog_bookmarks`
- `devlog_reposts`
- `devlog_tags`

Development also has `ensure_runtime_schema()` in `app/__init__.py`, which applies additive SQLite-only user columns for older local databases. Treat that as a local compatibility helper, not a production migration substitute.

## Seed Data

`populate_data.py` is idempotent and creates:

- Default categories.
- Default tags.
- Admin account.
- Demo account.
- A welcome blog.
- A sample project.
- Starter messages and notification.

Run it manually with:

```powershell
.\venv\Scripts\python.exe populate_data.py
```
