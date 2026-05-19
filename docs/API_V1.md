# API v1

Base path: `/api/v1`

Responses use a consistent envelope:

```json
{"ok": true, "data": {}, "meta": {}}
```

Errors use:

```json
{"ok": false, "error": {"code": "bad_request", "message": "Readable message", "details": {}}}
```

## Endpoints

- `GET /api/v1/health` - database-backed health check.
- `GET /api/v1/jobs?page=1&per_page=20&q=python&mode=remote&category=web` - paginated active jobs.
- `GET /api/v1/search?q=robotics` - users, blogs, and projects with basic relevance filtering.

## Production Notes

- API routes are rate limited with the existing limiter and should use Redis storage in production.
- Prefer cursor pagination for high-volume tables in future versions.
- Add token-scoped authentication before exposing private user, hiring, or collaboration writes.
