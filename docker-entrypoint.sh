#!/bin/sh
set -e

if [ "${APP_ENV:-}" = "production" ] && [ "${SKIP_PRODUCTION_CHECK:-false}" != "true" ]; then
  flask --app app:create_app production-check
fi

if [ "${SKIP_DB_MIGRATIONS:-false}" != "true" ]; then
  flask --app app:create_app deploy-db
fi

exec "$@"
