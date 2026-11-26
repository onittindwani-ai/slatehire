# Operating and backups

## Every day
Open Approvals and the Pipeline. The top banner shows the mode and the kill switch.

## Every week
Check Integrations (a failed test shows in words), read the Audit log tail, and run **Check the chain** (it must say intact).

## Retention
The worker deletes people who were declined or withdrawn longer ago than `RETENTION_DAYS`. Hired people are never swept: that is an employment record, so your own rules apply. The owner can delete a person at any time from the candidate page.

## Backups
- SQLite: copy the database file while the API is stopped, or use the `.backup` command.
- Postgres: `pg_dump` nightly to storage outside the server. `deploy/hetzner/backup.sh` does this for the Compose setup, with a copy of the exports folder, an empty dump treated as a failure and files readable by the owner only. Encrypt them before they leave the machine; they hold candidate data. The newest 14 of each are kept, and with `BACKUP_COPY_TO` set the other machine mirrors that (`rsync --delete`), so an old backup that rotates out here is removed there too. Use a folder on that machine that holds nothing else. The copy stops, and leaves the other machine as it was, when one run would remove more than `BACKUP_MAX_DELETE` files there (default 5, a normal run removes at most 3), so an empty or unmounted backup folder can never empty the copy.
- The export folder holds offer files. Back it up with the database.
- Every deletion appends the one way hashes of the person (nothing readable) to `erased-hashes.txt` in the export folder. Each backup saves a copy as `erased-hashes-<time>.txt` and adds it to `erased-hashes-all.txt`, a list that only grows and is never rotated. Every line carries the time it was written and the list keeps each line once, in the order it was first seen (it is not sorted), because the newest line for a person wins: when the owner lets someone back in (`/api/suppression/lift`) a line ending in `lift` is added.

## Restore, and erase again
A restore brings back the people who were deleted after the backup was made. Run it like this on the Compose server:

```
sh deploy/hetzner/restore.sh /var/backups/slatehire/slatehire-<time>.dump /var/backups/slatehire/exports-<time>.tar
```

Before it stops anything it reads the live erased list from the volume (it holds the erasures made since the last backup, up to a day of them), keeps a copy of it next to the dump (`erased-hashes-before-restore-<time>.txt`, never rotated) and merges it into `erased-hashes-all.txt`. It then stops the API and the worker, replaces the database, restores the exports, writes the merged list back into the volume (the exports archive holds an older copy that would otherwise replace it) and runs `python -m slatehire.reapply -` with the merged list: every hash in the list is remembered again and every live person who matches one is deleted again. It prints how many, and how many people it left alone because they were let back in later. It needs the same `SUPPRESSION_KEY` in `.env` that the data was erased under, which is why the key is kept outside the database. Without the list (the file is missing) nobody is erased again and the script says so: delete the people who asked by hand. On SQLite copy the database file back, then run `python -m slatehire.reapply erased-hashes-all.txt`. Test a restore on a copy once, before you need it.

## The kill switch
Owner only, top bar, Pause all. It stops calendar invites and offer files at once. Turn it off from the banner.
