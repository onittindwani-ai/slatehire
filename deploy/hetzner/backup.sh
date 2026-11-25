#!/bin/sh
# Nightly backup of the Postgres database and the exports folder. Safe to run from cron: it moves to the repository folder itself.
#   BACKUP_DIR       where the files go (default /var/backups/slatehire)
#   BACKUP_COPY_TO   optional rsync target on ANOTHER machine, for example user@host:/backups/slatehire/ (a copy on the same disk is not a backup).
#                    It must be a folder used only for these backups: the copy mirrors this folder, so a backup that is rotated out here is removed there too
#                    (otherwise a person who asked to be deleted would stay in an old copy for ever).
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
# The list of people erased since (one way hashes only, nothing readable). The app appends to it in the exports folder; each backup keeps a copy, and one list holds every hash ever seen and
# is never rotated, so after a restore deploy/hetzner/restore.sh can erase again whoever asked after the restored backup was made.
ERASED="$OUT/erased-hashes-$STAMP.txt"
docker compose exec -T api sh -c 'cat /data/exports/erased-hashes.txt 2>/dev/null || true' > "$ERASED.partial" || true
if [ -s "$ERASED.partial" ]; then
  mv -- "$ERASED.partial" "$ERASED"
  cat "$OUT/erased-hashes-all.txt" "$ERASED" 2>/dev/null | sort -u > "$OUT/erased-hashes-all.txt.partial"
  mv -- "$OUT/erased-hashes-all.txt.partial" "$OUT/erased-hashes-all.txt"
else
  rm -f -- "$ERASED.partial"
fi
# keep the newest 14 of each
ls -1t "$OUT"/slatehire-*.dump | tail -n +15 | while read -r old; do rm -f -- "$old"; done
ls -1t "$OUT"/exports-*.tar 2>/dev/null | tail -n +15 | while read -r old; do rm -f -- "$old"; done
ls -1t "$OUT"/erased-hashes-2*.txt 2>/dev/null | tail -n +15 | while read -r old; do rm -f -- "$old"; done
if [ -n "${BACKUP_COPY_TO:-}" ]; then
  rsync -a --delete "$OUT"/ "$BACKUP_COPY_TO"
  echo "copied to $BACKUP_COPY_TO"
fi
echo "wrote $DUMP"
