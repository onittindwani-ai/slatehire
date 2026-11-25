#!/bin/sh
# Restore a backup made by backup.sh, then erase again everyone who asked to be deleted after that backup was made.
#   sh deploy/hetzner/restore.sh /var/backups/slatehire/slatehire-20261125-0300.dump [/var/backups/slatehire/exports-20261125-0300.tar]
# It needs the same SUPPRESSION_KEY in .env that the data was erased under. The list of erased people is read from erased-hashes-all.txt in the folder of the dump.
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
LIST="$(dirname "$DUMP")/erased-hashes-all.txt"
docker compose stop api worker
docker compose exec -T db pg_restore -U slatehire -d slatehire --clean --if-exists --no-owner < "$DUMP"
docker compose up -d api worker
if [ -n "$EXPORTS" ] && [ -s "$EXPORTS" ]; then
  docker compose exec -T api tar -C /data -xf - < "$EXPORTS"
fi
if [ -s "$LIST" ]; then
  # the list is read from the standard input, and the command prints how many people it deleted again
  docker compose exec -T api python -m slatehire.reapply - < "$LIST"
else
  echo "no erased list found next to the dump ($LIST): nobody was erased again. If people asked to be deleted after this backup, delete them again by hand." >&2
fi
echo "restored $DUMP"
