# Operating and backups

## Every day
Open Approvals and the Pipeline. The top banner shows the mode and the kill switch.

## Every week
Check Integrations (a failed test shows in words), read the Audit log tail, and run **Check the chain** (it must say intact).

## Retention
The worker deletes people who were declined or withdrawn longer ago than `RETENTION_DAYS`. Hired people are never swept: that is an employment record, so your own rules apply. The owner can delete a person at any time from the candidate page.

## Backups
- SQLite: copy the database file while the API is stopped, or use the `.backup` command.
- Postgres: `pg_dump` nightly to storage outside the server. `deploy/hetzner/backup.sh` does this for the Compose setup, with a copy of the exports folder, an empty dump treated as a failure and files readable by the owner only. Encrypt them before they leave the machine; they hold candidate data. Test a restore once.
- The export folder holds offer files. Back it up with the database.

A restore brings back deleted people. If you restore after a deletion request, delete them again.

## The kill switch
Owner only, top bar, Pause all. It stops calendar invites and offer files at once. Turn it off from the banner.
