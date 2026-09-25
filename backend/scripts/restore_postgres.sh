#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"
test -f "$BACKUP_FILE"
if [[ -f "${BACKUP_FILE}.sha256" ]]; then sha256sum -c "${BACKUP_FILE}.sha256"; fi
pg_restore --dbname="$DATABASE_URL" --clean --if-exists --no-owner --no-privileges --exit-on-error "$BACKUP_FILE"
