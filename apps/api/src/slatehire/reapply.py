"""After a restore: erase again whoever was erased after the backup was made.

A restore brings back the database as it was on the day of the backup, including people who asked to be deleted later. Every erasure appends the keyed hashes of the person to
`erased-hashes.txt` in the export folder, and the backup script keeps a copy of that list, with every earlier one, next to each dump. This command reads such a list, remembers every hash
in it, and deletes any live person whose address or outside reference matches one. A person the owner let back in later (`/api/suppression`) has a line that ends in `lift`: the newest line
for a hash wins, so a lifted person is not deleted again. It needs the same SUPPRESSION_KEY the data was erased under (hashes made with another key match nobody).

    python -m slatehire.reapply erased-hashes-all.txt      (or - to read the list from the standard input)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from slatehire import retention, suppression
from slatehire.models import Application, Candidate, Suppression


class Entry(NamedTuple):
    digest: str
    kind: str
    group: str
    at: int = 0  # when the line was written (nanoseconds); a line from before times existed is 0
    lifted: bool = False  # the person was let back in on purpose: this line undoes an earlier erasure


def read_list(text: str) -> list[Entry]:
    """The lines of an erased list: (digest, kind, group, time, lifted). A line that is not a hash is skipped, so a damaged list never stops the rest. Older lines are `digest kind group`."""
    out: list[Entry] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 64 and all(c in "0123456789abcdef" for c in parts[0]) and parts[1] in ("email", "ref"):
            rest = parts[3:]
            at = next((int(x) for x in rest if x.isdigit()), 0)
            group = parts[2] if len(parts) > 2 and parts[2] != "-" else ""
            out.append(Entry(parts[0], parts[1], group, at, "lift" in rest))
    return out


def final_state(entries: list[Entry]) -> dict[str, Entry]:
    """The newest line for each hash. A hash whose newest line is a lift is not erased. Equal times keep the order of the file."""
    newest: dict[str, tuple[int, int, Entry]] = {}
    for n, e in enumerate(entries):
        if e.digest not in newest or (e.at, n) >= newest[e.digest][:2]:
            newest[e.digest] = (e.at, n, e)
    return {d: v[2] for d, v in newest.items()}


def apply(s: Session, entries: list[Entry], now, export_dir: str | Path | None = None) -> dict:
    """Bring a restored database up to date with an erased list: remember every hash whose newest line is an erasure, forget every hash whose newest line is a lift, and delete each live person
    who matches an erased hash. Returns what was done."""
    state = final_state([e if isinstance(e, Entry) else Entry(*e) for e in entries])
    erased = {d: e for d, e in state.items() if not e.lifted}
    let_back = {d for d, e in state.items() if e.lifted}
    have = set(s.scalars(select(Suppression.digest)))
    added = 0
    for digest, e in erased.items():
        if digest not in have:
            s.add(Suppression(digest=digest, kind=e.kind, scheme="key", group_id=e.group, created_at=now))
            have.add(digest)
            added += 1
    lifted = int(s.execute(delete(Suppression).where(Suppression.digest.in_(let_back), Suppression.scheme == "key")).rowcount or 0) if let_back else 0
    s.flush()
    wanted = set(erased)
    deleted = 0
    for cand in list(s.scalars(select(Candidate).where(Candidate.purged_at.is_(None)))):
        if suppression.digests_of(s, cand.email, cand.source, cand.external_ref) & wanted:
            for app in list(s.scalars(select(Application).where(Application.candidate_id == cand.id))):
                retention.purge(s, app, "restore", now, "erased again after a restore", export_dir)
                deleted += 1
    return {"hashes_added": added, "hashes_lifted": lifted, "people_deleted": deleted, "lines": len(entries)}


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
    print(f"reapplied: {out['lines']} lines, {out['hashes_added']} new hashes, {out['hashes_lifted']} lifted, {out['people_deleted']} people deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
