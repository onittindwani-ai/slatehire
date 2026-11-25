#!/bin/sh
# Nightly backup of the Postgres database and the exports folder. Safe to run from cron: it moves to the repository folder itself.
#   BACKUP_DIR       where the files go (default /var/backups/slatehire)
#   BACKUP_COPY_TO   optional rsync target on ANOTHER machine, for example user@host:/backups/slatehire/ (a copy on the same disk is not a backup)
# The files hold candidate data. They are created readable by the owner only (umask 077); encrypt them before they leave the machine.
set -eu
umask 077
cd "$(dirname "$0")/../.."
OUT="${BACKUP_DIR:-/var/backups/slatehire}"
mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M)
DUMP="$OUT/slatehire-$STAMP.dump"
EXPORTS="$OUT/exports-$STAMP.tar"
TMP_DUMP="$DUMP.partial"
TMP_EXPORTS="$EXPORTS.partial"
trap 'rm -f -- "$TMP_DUMP" "$TMP_EXPORTS"' EXIT
# Write to a partial file first, so a failed dump never counts as a backup and never pushes a good one out of the rotation.
docker compose exec -T db pg_dump -U slatehire -Fc slatehire > "$TMP_DUMP"
if [ ! -s "$TMP_DUMP" ]; then
  echo "backup failed: the database dump is empty" >&2
  exit 1
fi
mv -- "$TMP_DUMP" "$DUMP"
# The exports folder holds the offer letters and files the app wrote. It may be empty, so a failure here is not fatal.
docker compose exec -T api tar -C /data -cf - exports > "$TMP_EXPORTS" || true
if [ -s "$TMP_EXPORTS" ]; then mv -- "$TMP_EXPORTS" "$EXPORTS"; fi
# keep the newest 14 of each
ls -1t "$OUT"/slatehire-*.dump | tail -n +15 | while read -r old; do rm -f -- "$old"; done
ls -1t "$OUT"/exports-*.tar 2>/dev/null | tail -n +15 | while read -r old; do rm -f -- "$old"; done
if [ -n "${BACKUP_COPY_TO:-}" ]; then
  rsync -a "$OUT"/ "$BACKUP_COPY_TO"
  echo "copied to $BACKUP_COPY_TO"
fi
echo "wrote $DUMP"
