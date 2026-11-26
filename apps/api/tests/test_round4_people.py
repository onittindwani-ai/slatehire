"""Round 4, erasure and restore: a person let back in stays in after a restore, the live list survives it, the copy to another machine cannot be emptied by an empty folder. Each test fails on the code before the fix."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from sqlalchemy import select

from hardening_helpers import OWNER, RESUME, real_ctx, real_settings
from slatehire import intake, reapply, retention, suppression
from slatehire.context import Ctx
from slatehire.dbsetup import make_private_engine
from slatehire.ingest import Applicant
from slatehire.models import Application, Candidate, Role, Suppression
from sendora_core.db import make_session_factory

ROOT = Path(__file__).resolve().parents[3]
MAIL = "ann@mail.example.test"


def add_ann(s, ctx, role) -> Application:
    app, status = intake.add_applicant(s, Applicant("Ann Vale", MAIL, "", role.key, RESUME, "", "paste"), role, "x", ctx.now(s), settings=ctx.settings)
    assert status == "added", status
    s.commit()
    return app


def live_people(s) -> list[str]:
    return [c.full_name for c in s.scalars(select(Candidate).where(Candidate.purged_at.is_(None)))]


def start(tmp_path):
    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        role = Role(key="support", title="Support")
        s.add(role)
        s.commit()
    return ctx


# ---- a person who was let back in is not deleted again by a restore ----

def test_a_person_erased_then_let_back_in_and_added_again_is_not_deleted_by_the_list(tmp_path):
    ctx = start(tmp_path)
    export = ctx.settings.export_dir
    with ctx.factory() as s:
        role = s.scalars(select(Role)).first()
        app = add_ann(s, ctx, role)
        retention.purge_person(s, app, OWNER, ctx.now(s), "on request", export)
        s.commit()
        assert suppression.lift(s, MAIL, OWNER) == 1
        s.commit()
        add_ann(s, ctx, role)  # she applied again on purpose
        listed = (Path(export) / suppression.ERASED_LIST).read_text()
        out = reapply.apply(s, reapply.read_list(listed), ctx.now(s), export)
        s.commit()
        assert out["people_deleted"] == 0 and live_people(s) == ["Ann Vale"]
        assert not suppression.is_suppressed(s, MAIL, "paste", None)  # and the hash is gone from the database too


def test_the_list_says_when_each_line_was_written_and_a_lift_is_a_line_of_its_own(tmp_path):
    ctx = start(tmp_path)
    export = ctx.settings.export_dir
    with ctx.factory() as s:
        app = add_ann(s, ctx, s.scalars(select(Role)).first())
        retention.purge_person(s, app, OWNER, ctx.now(s), "on request", export)
        s.commit()
        suppression.lift(s, MAIL, OWNER)
        s.commit()
    lines = (Path(export) / suppression.ERASED_LIST).read_text().splitlines()
    parsed = reapply.read_list("\n".join(lines))
    assert [e.lifted for e in parsed] == [False, True] and all(e.at > 0 for e in parsed) and parsed[0].at < parsed[1].at
    assert lines[-1].endswith(" lift") and MAIL not in "\n".join(lines)


def test_erase_lift_erase_again_within_a_second_still_ends_erased(tmp_path):
    ctx = start(tmp_path)
    export = ctx.settings.export_dir
    with ctx.factory() as s:
        role = s.scalars(select(Role)).first()
        retention.purge_person(s, add_ann(s, ctx, role), OWNER, ctx.now(s), "on request", export)
        s.commit()
        suppression.lift(s, MAIL, OWNER)
        s.commit()
        retention.purge_person(s, add_ann(s, ctx, role), OWNER, ctx.now(s), "on request again", export)
        s.commit()
    listed = (Path(export) / suppression.ERASED_LIST).read_text()
    restored_db = tmp_path / "old.sqlite3"
    engine = make_private_engine(f"sqlite:///{restored_db}")
    from sendora_core.db import Base

    Base.metadata.create_all(engine)
    restored = Ctx(real_settings(tmp_path, database_url=f"sqlite:///{restored_db}"), make_session_factory(engine))
    with restored.factory() as s:
        role = Role(key="support", title="Support")
        s.add(role)
        s.flush()
        s.add(Candidate(code="C0001", full_name="Ann Vale", email=MAIL, source="paste", created_at=restored.now(s)))
        s.flush()
        s.add(Application(candidate_id=s.scalars(select(Candidate)).first().id, role_id=role.id, stage="applied", history=[]))
        s.flush()
        shuffled = "\n".join(reversed(listed.splitlines()))  # the file may reach the command in any order: the time on each line decides
        out = reapply.apply(s, reapply.read_list(shuffled), restored.now(s), restored.settings.export_dir)
        assert out["people_deleted"] == 1 and suppression.is_suppressed(s, MAIL, "paste", None)


def test_older_lines_without_a_time_still_read_and_are_the_oldest():
    old = "a" * 64 + " email g1\n" + "a" * 64 + " email g1 5 lift\n"
    got = reapply.read_list(old)
    assert [(e.at, e.lifted) for e in got] == [(0, False), (5, True)] and reapply.final_state(got)["a" * 64].lifted is True


def test_a_lift_of_an_old_salted_hash_writes_no_line_because_the_list_holds_only_keyed_hashes(tmp_path):
    import hashlib
    import hmac

    from slatehire.models import State

    ctx = real_ctx(tmp_path)
    with ctx.factory() as s:
        s.add(State(key=suppression.SALT_KEY, value="oldsalt"))
        s.add(Suppression(digest=hmac.new(b"oldsalt", b"email:old@mail.example.test", hashlib.sha256).hexdigest(), kind="email", scheme="salt", created_at=ctx.now(s)))
        s.commit()
        assert suppression.lift(s, "old@mail.example.test", OWNER) == 1
        s.commit()
    assert not (Path(ctx.settings.export_dir) / suppression.ERASED_LIST).exists()


# ---- restore.sh ----

def fake_docker(tmp_path, live: str) -> tuple[Path, Path]:
    """A `docker` that logs every call in order, answers the read of the live list with `live`, and keeps what is written back and what is handed to the reapply command."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    (tmp_path / "live.txt").write_text(live)
    script = (f'#!/bin/sh\necho "docker $*" >> "{log}"\n'
              f'case "$*" in\n'
              f'  *"cat /data/exports/erased-hashes.txt"*) cat "{tmp_path / "live.txt"}";;\n'
              f'  *"cat > /data/exports/erased-hashes.txt"*) cat > "{tmp_path / "written-back.txt"}";;\n'
              f'  *reapply*) cat > "{tmp_path / "reapply-input.txt"}";;\n'
              f'  *"tar -C /data -xf -"*) cat > /dev/null;;\n'
              f'esac\n')
    (bin_dir / "docker").write_text(script)
    (bin_dir / "docker").chmod(0o755 | stat.S_IEXEC)
    return bin_dir, log


def run_restore(tmp_path, bin_dir: Path, *args: str):
    root = tmp_path / "repo"
    (root / "deploy" / "hetzner").mkdir(parents=True, exist_ok=True)
    (root / "deploy" / "hetzner" / "restore.sh").write_text((ROOT / "deploy" / "hetzner" / "restore.sh").read_text())
    return subprocess.run(["sh", str(root / "deploy" / "hetzner" / "restore.sh"), *args], capture_output=True, text=True, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}, timeout=60)


def test_a_restore_reads_the_live_list_before_stopping_and_puts_the_merged_list_back_after_the_exports(tmp_path):
    new = "b" * 64 + " email g2 20"
    old = "a" * 64 + " email g1 10"
    bin_dir, log = fake_docker(tmp_path, new + "\n")
    out = tmp_path / "backups"
    out.mkdir()
    dump, tar = out / "slatehire-1.dump", out / "exports-1.tar"
    dump.write_text("DUMP")
    tar.write_text("TAR")
    (out / "erased-hashes-all.txt").write_text(old + "\n")
    done = run_restore(tmp_path, bin_dir, str(dump), str(tar))
    assert done.returncode == 0, done.stderr
    calls = log.read_text()
    order = [calls.index(x) for x in ("cat /data/exports/erased-hashes.txt", "compose stop", "pg_restore", "tar -C /data", "cat > /data/exports/erased-hashes.txt", "reapply")]
    assert order == sorted(order)  # read the live list, stop, restore, unpack the exports, write the merged list back, erase again
    merged = {line for line in (tmp_path / "written-back.txt").read_text().splitlines()}
    assert merged == {old, new}  # the erasure made after the backup is not lost to the old copy inside the exports
    assert {line for line in (tmp_path / "reapply-input.txt").read_text().splitlines()} == {old, new}
    assert {line for line in (out / "erased-hashes-all.txt").read_text().splitlines()} == {old, new}  # the list next to the dump has it too
    kept = list(out.glob("erased-hashes-before-restore-*.txt"))
    assert len(kept) == 1 and kept[0].read_text().strip() == new  # a copy of the live list, outside the data folder, that no rotation removes


def test_a_restore_with_no_readable_live_list_says_so_and_still_uses_the_list_next_to_the_dump(tmp_path):
    bin_dir, log = fake_docker(tmp_path, "")
    out = tmp_path / "backups"
    out.mkdir()
    dump = out / "slatehire-1.dump"
    dump.write_text("DUMP")
    (out / "erased-hashes-all.txt").write_text("a" * 64 + " email g1 10\n")
    done = run_restore(tmp_path, bin_dir, str(dump))
    assert done.returncode == 0 and "live erased list could not be read" in done.stderr
    assert ("a" * 64) in (tmp_path / "reapply-input.txt").read_text()


# ---- backup.sh ----

def run_backup(tmp_path, out: Path, rsync_exit: int = 0):
    root = tmp_path / "repo"
    (root / "deploy" / "hetzner").mkdir(parents=True, exist_ok=True)
    (root / "deploy" / "hetzner" / "backup.sh").write_text((ROOT / "deploy" / "hetzner" / "backup.sh").read_text())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "rsync.log"
    (bin_dir / "docker").write_text('#!/bin/sh\ncase "$*" in\n*pg_dump*) echo DUMP;;\n*"tar -C /data"*) echo TAR;;\n*erased-hashes*) printf "%s\\n" "cc email g3 30";;\nesac\n')
    (bin_dir / "rsync").write_text(f'#!/bin/sh\necho "rsync $*" >> "{log}"\nexit {rsync_exit}\n')
    for f in bin_dir.iterdir():
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "BACKUP_DIR": str(out), "BACKUP_COPY_TO": "user@host:/backups/slatehire/"}
    return subprocess.run(["sh", str(root / "deploy" / "hetzner" / "backup.sh")], capture_output=True, text=True, env=env, timeout=60), log


def test_the_copy_to_another_machine_cannot_remove_more_than_a_normal_run_does(tmp_path):
    out = tmp_path / "backups"
    out.mkdir()
    done, log = run_backup(tmp_path, out)
    assert done.returncode == 0, done.stderr
    assert "--max-delete=5" in log.read_text() and "--delete" in log.read_text()
    stopped, _ = run_backup(tmp_path / "second", out, rsync_exit=25)  # what rsync answers when an unmounted, empty folder would have emptied the other machine
    assert stopped.returncode != 0 and "stopped" in stopped.stderr and "mounted" in stopped.stderr


def test_the_all_list_keeps_each_line_once_in_the_order_it_was_first_seen(tmp_path):
    out = tmp_path / "backups"
    out.mkdir()
    (out / "erased-hashes-all.txt").write_text("zz email g9 5\naa email g1 1 lift\n")
    done, _ = run_backup(tmp_path, out)
    assert done.returncode == 0, done.stderr
    assert (out / "erased-hashes-all.txt").read_text().splitlines() == ["zz email g9 5", "aa email g1 1 lift", "cc email g3 30"]  # not sorted: the order the file was written in is kept
