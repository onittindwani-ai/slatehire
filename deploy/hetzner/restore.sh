#!/bin/sh
# Restore a backup made by backup.sh, then erase again everyone who asked to be deleted after that backup was made.
#   sh deploy/hetzner/restore.sh /var/backups/slatehire/slatehire-20261125-0300.dump [/var/backups/slatehire/exports-20261125-0300.tar]
# It needs the same SUPPRESSION_KEY in .env that the data was erased under.
# The list of erased people is the one next to the dump (erased-hashes-all.txt) AND the live one on the volume, which holds the newest erasures: it is read BEFORE anything is stopped, kept
# next to the dump (erased-hashes-before-restore-<time>.txt, never rotated), merged, and written back into the volume after the exports are restored, so the old copy inside the exports
# archive never replaces it.
# It stops the API and the worker while the database is replaced, and starts them again at the end.
set -eu
umask 077
cd "$(dirname "$0")/../.."
DUMP="${1:-}"
EXPORTS="${2:-}"
if [ -z "$DUMP" ] || [ ! -s "$DUMP" ]; then
  echo "usage: sh deploy/hetzner/restore.sh <dump file> [exports tar]   (the dump must exist and not be empty)" >&2
  exit 1
fi
OUT="$(dirname "$DUMP")"
LIST="$OUT/erased-hashes-all.txt"
LIVE="$OUT/erased-hashes-before-restore-$(date +%Y%m%d-%H%M%S).txt"
MERGED="$LIST.merged"
trap 'rm -f -- "$MERGED"' EXIT
# 1. the live list, while the API can still be asked (when it is already stopped, ask the stopped container for the file)
if ! docker compose exec -T api sh -c 'cat /data/exports/erased-hashes.txt 2>/dev/null || true' > "$LIVE" 2>/dev/null; then
  docker compose cp api:/data/exports/erased-hashes.txt "$LIVE" >/dev/null 2>&1 || : > "$LIVE"
fi
if [ ! -s "$LIVE" ]; then
  echo "warning: the live erased list could not be read (or is empty), so only the list next to the dump is used. If people asked to be deleted since the last backup, check them by hand." >&2
fi
# 2. merge: every line once, in the order first seen (each line carries its own time and the newest line for a person wins)
cat "$LIST" "$LIVE" 2>/dev/null | awk 'NF && !seen[$0]++' > "$MERGED" || true
if [ -s "$MERGED" ]; then cp -- "$MERGED" "$LIST"; fi
docker compose stop api worker
docker compose exec -T db pg_restore -U slatehire -d slatehire --clean --if-exists --no-owner < "$DUMP"
docker compose up -d api worker
if [ -n "$EXPORTS" ] && [ -s "$EXPORTS" ]; then
  docker compose exec -T api tar -C /data -xf - < "$EXPORTS"
fi
if [ -s "$MERGED" ]; then
  # the archive just brought back the old list: put the merged one in its place, so the next backup and the next restore have every erasure
  docker compose exec -T api sh -c 'cat > /data/exports/erased-hashes.txt && chmod 600 /data/exports/erased-hashes.txt' < "$MERGED"
  # the list is read from the standard input, and the command prints how many people it deleted again
  docker compose exec -T api python -m slatehire.reapply - < "$MERGED"
else
  echo "no erased list found (next to the dump: $LIST, or on the volume): nobody was erased again. If people asked to be deleted after this backup, delete them again by hand." >&2
fi
echo "restored $DUMP"
