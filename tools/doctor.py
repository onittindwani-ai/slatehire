"""Check your setup in plain words. It never prints a secret, only the names of variables.

    python tools/doctor.py            checks settings and every selected adapter that works offline
    python tools/doctor.py --live     also tests the real services you selected (this makes network calls, but sends nothing)
"""

from __future__ import annotations

import sys

import _common  # noqa: F401
from slatehire.config import Settings
from slatehire.registry import CATEGORIES, ENV_VARS, build_adapters, build_registry
from sendora_core.adapters import AdapterError
from sendora_core.db import make_engine
from sqlalchemy import text


def main(argv: list[str]) -> int:
    live = "--live" in argv
    bad = 0
    try:
        s = Settings()
    except Exception as exc:
        print(f"FAIL settings: {type(exc).__name__}. Check the names and values in your environment file.")
        return 1
    print(f"mode={s.mode.value} demo_mode={s.demo_mode} kill_switch={s.kill_switch} llm_mode={s.llm_mode.value}")
    for p in s.problems():
        print("PROBLEM", p)
        bad += 1
    try:
        with make_engine(s.database_url).connect() as c:
            c.execute(text("SELECT 1"))
        print("OK   database reachable")
    except Exception as exc:
        print(f"FAIL database: {type(exc).__name__}. Check DATABASE_URL.")
        bad += 1
    chosen = {c: getattr(s, f"{c}_adapter") for c in CATEGORIES}
    for cat, name in chosen.items():
        need = ENV_VARS.get((cat, name), [])
        missing = [v for v in need if not getattr(s, v.lower(), "")]
        if missing and name not in {"seed", "package"}:
            print(f"FAIL {cat}/{name}: set {', '.join(missing)}")
            bad += 1
            continue
        if name in {"seed", "package"} or live:
            try:
                ok, detail = build_adapters(s)[cat].healthcheck()
            except AdapterError as exc:
                ok, detail = False, str(exc)
            print(("OK   " if ok else "FAIL ") + f"{cat}/{name}: {detail}")
            bad += 0 if ok else 1
        else:
            print(f"SKIP {cat}/{name}: variables are set; run with --live to test the connection")
    reg = build_registry(s)
    print(f"adapters known: {len(reg.describe())}, none verified live by this project")
    print("RESULT", "all good" if not bad else f"{bad} problem(s) to fix")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
