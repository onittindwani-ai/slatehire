"""After a restore: erase again whoever was erased after the backup was made.

A restore brings back the database as it was on the day of the backup, including people who asked to be deleted later. Every erasure appends the keyed hashes of the person to
`erased-hashes.txt` in the export folder, and the backup script keeps a copy of that list, with every earlier one, next to each dump. This command reads such a list, remembers every hash
in it, and deletes any live person whose address or outside reference matches one. It needs the same SUPPRESSION_KEY the data was erased under (hashes made with another key match nobody).

    python -m slatehire.reapply erased-hashes-all.txt      (or - to read the list from the standard input)
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import retention, suppression
from slatehire.models import Application, Candidate, Suppression


def read_list(text: str) -> list[tuple[str, str, str]]:
    """(digest, kind, group) from each line of an erased list. A line that is not a hash is skipped, so a damaged list never stops the rest."""
    out: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 64 and all(c in "0123456789abcdef" for c in parts[0]) and parts[1] in ("email", "ref"):
            out.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    return out


def apply(s: Session, entries: list[tuple[str, str, str]], now, export_dir: str | Path | None = None) -> dict:
    """Remember every hash of the list, then delete each live person who matches one. Returns what was done."""
    have = set(s.scalars(select(Suppression.digest)))
    added = 0
    for digest, kind, group in entries:
        if digest not in have:
            s.add(Suppression(digest=digest, kind=kind, scheme="key", group_id=group, created_at=now))
            have.add(digest)
            added += 1
    s.flush()
    wanted = {d for d, _k, _g in entries}
    deleted = 0
    for cand in list(s.scalars(select(Candidate).where(Candidate.purged_at.is_(None)))):
        if suppression.digests_of(s, cand.email, cand.source, cand.external_ref) & wanted:
            for app in list(s.scalars(select(Application).where(Application.candidate_id == cand.id))):
                retention.purge(s, app, "restore", now, "erased again after a restore", export_dir)
                deleted += 1
    return {"hashes_added": added, "people_deleted": deleted, "lines": len(entries)}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    text = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    from slatehire.worker import setup

    settings, ctx, _worker = setup()
    if not settings.suppression_key_ok():
        print("SUPPRESSION_KEY is not set (32 or more characters). Without the key the hashes in the list cannot be matched.", file=sys.stderr)
        return 1
    from sendora_core.db import session_scope

    with session_scope(ctx.write_factory) as s:
        out = apply(s, read_list(text), ctx.now(s), settings.export_dir)
    print(f"reapplied: {out['lines']} lines, {out['hashes_added']} new hashes, {out['people_deleted']} people deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
