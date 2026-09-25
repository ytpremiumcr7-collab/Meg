#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:=/var/backups/megalodon}"
mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
outfile="$BACKUP_DIR/megalodon_${stamp}.dump"
pg_dump "$DATABASE_URL" --format=custom --no-owner --no-privileges --file="$outfile"
sha256sum "$outfile" > "${outfile}.sha256"
echo "$outfile"
