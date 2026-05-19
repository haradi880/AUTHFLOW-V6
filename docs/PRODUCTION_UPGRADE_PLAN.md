# Production Upgrade Plan

## Existing Issues Found

- Job applications were persisted, but applicants only received a flash message and recruiters had no dependable application event trail.
- Notifications existed as simple unread rows, with no delivery metadata, seen timestamp, entity reference, or application-specific email semantics.
- Recruiters had no protected workflow to review applications, update statuses, or send structured responses.
- Collaboration was represented indirectly through messages/projects, but there were no team workspaces, invitations, request lifecycle, activity stream, or role checks.
- Job browsing used a visually heavy layout with broken encoded symbols, limited search scope, weak mobile ergonomics, and no obvious application tracking path.
- Hiring queries lacked composite indexes for the common filters: status, category, type, work mode, company, and application status.
- Security foundations existed: CSRF, rate limiting, secure headers, login lockout, password hashing, email verification/reset flows, cookie consent copy, and audit logging. The remaining production work is operational hardening: Redis-backed rate limits, monitored async jobs, CSP tightening, data export/deletion workflows, and deployment secrets discipline.

## Implemented Architecture Upgrades

- Added richer `Notification` fields: `seen_at`, `read_at`, `delivered_at`, `email_sent_at`, `priority`, `entity_type`, and `entity_id`.
- Added application tracking fields: `recruiter_response`, `status_changed_at`, and `reviewed_by_id`.
- Added collaboration models: `Team`, `TeamMember`, `TeamInvitation`, `CollaborationRequest`, and `ActivityUpdate`.
- Added composite indexes for notification history, application queues, job filters, team membership, invites, collaboration inboxes, and activity streams.
- Added `/api/pulse`, `/api/notifications`, and `/api/notifications/read` support for reliable near-real-time polling and explicit seen/read state.
- Added migration `20260519_0004_notifications_collaboration_hiring.py` for a repeatable schema rollout.

## UX Upgrades

- Rebuilt `/hiring` into a responsive job marketplace with accessible search, sticky filters, clean job cards, reset flow, and clearer CTAs.
- Rebuilt job detail application UX with a dedicated apply panel, cover note, save action, and application status display.
- Added `/hiring/applications` for applicant-side status tracking.
- Added recruiter application management at `/hiring/jobs/<job_id>/applications`.
- Added `/collaboration` team hub, team creation, team detail, invitation handling, and collaboration request response flows.
- Added settings security center with active devices, login history, suspicious login indicators, remote device removal, and logout-all controls.
- Added UPI donation QR generation with persisted donation intents, mobile-first support UI, and donation success flow.
- Added admin monitoring view for audit logs, login events, and donation intents.

## Security Improvements

- Application/recruiter update routes enforce owner/company-owner/admin authorization.
- Collaboration routes enforce authenticated access, team role management, and per-recipient response permissions.
- New write routes are protected by existing Flask-WTF CSRF and route-level rate limiting where abuse risk is highest.
- Notification email failures are logged through the app logger instead of printed.
- Search/filtering uses SQLAlchemy expressions rather than raw SQL string interpolation.
- Login success/failure events are stored in the database and mirrored to audit logs without exposing password details.
- Session/device revocation is enforced on each authenticated request.

## Next Production Steps

1. Replace in-process notification polling with WebSocket or Server-Sent Events when deploying behind Redis or a managed pub/sub layer.
2. Move notification email dispatch to a real queue such as Celery/RQ/Arq so user requests are never slowed by SMTP/API latency.
3. Store structured skills in normalized tables or PostgreSQL arrays/trigram indexes instead of comma-separated strings.
4. Add account data export, deletion queue, consent ledger, and retention schedules for GDPR-style data handling.
5. Replace `memory://` rate limit storage with Redis in production.
6. Tighten CSP by removing inline script/style allowances after templates are migrated to nonce-based scripts and static CSS.
7. Add OpenTelemetry/Sentry integration for error tracing, performance metrics, and security event dashboards.
8. Add Playwright accessibility and responsive visual tests for the hiring and collaboration flows.
9. Run with Docker Compose using PostgreSQL, Redis-backed rate limits, Gunicorn, and Nginx via the included deployment files.
10. Use `/api/v1/health` and `/healthz` for uptime checks and deploy the `worker` service for notification/email queues.
