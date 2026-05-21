#!/bin/sh
set -e

if [ "${SKIP_DB_MIGRATIONS:-false}" != "true" ]; then
  flask deploy-db
fi

exec "$@"
