# Backup And Restore Runbook

## Backup Schedule

- Database: enable managed PostgreSQL daily backups and point-in-time recovery on the production provider.
- Storage: back up Supabase buckets `uploads`, `private-uploads`, and `backups`.
- App archive: create a HaradiBots admin backup before risky deploys, migrations, or bulk moderation work.

## Create A Backup

From the admin UI:

```text
/admin/backup
```

Select database, uploads, logs, and cloud upload when Supabase backup storage is configured.

From the CLI, use the admin UI-created archive verification:

```powershell
flask --app app:create_app backup-verify --name haradi_backup_YYYYMMDD_HHMMSS.zip
```

Create and verify a fresh CLI drill archive:

```powershell
flask --app app:create_app backup-drill --json
```

For a fast local app-files drill without a database dump:

```powershell
flask --app app:create_app backup-drill --skip-database --skip-logs --json
```

Or verify an explicit path:

```powershell
flask --app app:create_app backup-verify --path C:\backups\haradi_backup_YYYYMMDD_HHMMSS.zip
```

## What A Backup Contains

Each archive includes:

- `backup_manifest.json` with file names, sizes, SHA-256 checksums, include flags, app env, database scheme, and Alembic revision.
- `backup_manifest.txt` as a quick human-readable summary.
- Database dump or SQLite copy when database backup is selected.
- Uploads, instance files, migrations, and logs based on selected options.

## Restore Drill

1. Create or select a recent verified archive.
2. Confirm `backup-verify` exits successfully.
3. Restore PostgreSQL from managed backup or `database/postgres_dump.sql`.
4. Restore Supabase buckets from provider backup or synced object copy.
5. Deploy the matching app revision.
6. Run migrations:

```powershell
flask --app app:create_app db upgrade
```

7. Run preflight and smoke checks:

```powershell
flask --app app:create_app production-check
pytest -q -W error::sqlalchemy.exc.LegacyAPIWarning
```

8. Verify `/readyz`, login, public profiles, public blogs/projects, uploads, private message attachments, and admin backup page.

## Recovery Targets

- RPO target: 24 hours until managed PITR is enabled; lower after PITR is active.
- RTO target: 2 hours for a documented restore on the chosen production host.

These targets must be validated with an actual restore drill before calling the app production-ready.
