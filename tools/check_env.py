#!/usr/bin/env python3
"""Check an environment file against the repo's .env.example. Prints variable names only, never values.

Usage: python3 tools/check_env.py [--example .env.example] [--env .env] [--strict]

What it checks, in plain words:
  1. Every variable in .env.example exists in your environment file or your shell (a missing one is listed).
  2. Core variables are not left on a placeholder when DEMO_MODE is off.
  3. A group of settings (the comment line above them is the group name) that you started to fill in must be filled in completely.
     A group you left empty is treated as switched off, which is fine.
  4. Names in your file that the example does not know are listed (a typo is the usual reason).

Exit code 0 when nothing is wrong, 1 when there are problems. --strict also fails on unknown names.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"(change-?me|your[-_ ]|example|xxxx|replace)", re.I)
CORE_REQUIRED_LIVE = ("SESSION_SECRET", "DATABASE_URL")
LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def parse_example(text: str) -> list[tuple[str, str, str]]:
    """Return (group, name, default) for each variable in the example file."""
    group, out = "Core", []
    after_blank = True  # a comment names a group only when it follows a blank line; a note on the line above one variable does not
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            after_blank = True
            continue
        if line.startswith("#"):
            comment = line.lstrip("# ").strip()
            if after_blank and comment and not comment.lower().startswith(("copy to", "make the hash", "which adapter")):
                group = comment.split(".")[0][:60]
            after_blank = False
            continue
        after_blank = False
        m = LINE.match(line)
        if m:
            out.append((group, m.group(1), m.group(2).strip().strip("'\"")))
    return out


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        m = LINE.match(raw.strip())
        if m:
            values[m.group(1)] = m.group(2).strip().strip("'\"")
    return values


def check(example_text: str, env_text: str | None, shell: dict[str, str] | None = None, strict: bool = False) -> list[str]:
    problems: list[str] = []
    spec = parse_example(example_text)
    values = {**parse_env(env_text or ""), **(shell or {})}
    names = {n for _, n, _ in spec}
    if env_text is None and not shell:
        problems.append("No environment file found. Copy .env.example to .env first.")
    demo = values.get("DEMO_MODE", dict((n, d) for _, n, d in spec).get("DEMO_MODE", "true")).lower() == "true"
    for _, name, _ in spec:
        if name not in values:
            problems.append(f"{name} is missing. Add it to your environment file.")
    if not demo:
        for name in CORE_REQUIRED_LIVE:
            v = values.get(name, "")
            if not v or PLACEHOLDER.search(v):
                problems.append(f"{name} is empty or still a placeholder, and demo mode is off.")
    groups: dict[str, list[tuple[str, str]]] = {}
    for g, n, d in spec:
        groups.setdefault(g, []).append((n, d))
    for g, members in groups.items():
        if g == "Core" or not any(m in g.lower() for m in ("all or none", "fill in together")):
            continue  # only a group the example marks "all or none" or "fill in together" must be filled in completely
        no_default = [n for n, d in members if not d]
        started = [n for n, d in members if values.get(n, "") and values.get(n, "") != d]
        if started and no_default:
            empty = [n for n in no_default if not values.get(n, "")]
            if empty:
                problems.append(f"Group '{g}' is partly filled in. Still empty: {', '.join(empty)}.")
    if strict:
        for n in sorted(set(parse_env(env_text or "")) - names):
            problems.append(f"{n} is in your file but not in .env.example. Check the spelling.")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--example", default=".env.example")
    ap.add_argument("--env", default=".env")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    ex = Path(a.example)
    if not ex.is_file():
        print(f"FAIL {a.example} not found. Run this from the repo root.")
        return 1
    env_path = Path(a.env)
    env_text = env_path.read_text() if env_path.is_file() else None
    problems = check(ex.read_text(), env_text, dict(os.environ) if env_text is None else None, a.strict)
    for p in problems:
        print("PROBLEM", p)
    print("OK environment looks complete" if not problems else f"{len(problems)} problem(s). See docs/04-ENVIRONMENT-VARIABLES.md")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
