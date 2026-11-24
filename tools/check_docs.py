#!/usr/bin/env python3
"""Check the written docs before they ship. Exit 1 when anything is wrong.

  python3 tools/check_docs.py          check
  python3 tools/check_docs.py --fix    also rewrite quoted counts from data/counts.json

Checks: no em or en dashes, no local paths or private links, GitHub links are the repo home page only, every quoted count
(<!--n:path-->value<!--/n-->) equals data/counts.json, every relative link in the Markdown points at a file that exists,
no leftover words from other systems.
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import unquote
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHES = {chr(c) for c in (0x2014, 0x2013, 0x2012, 0x2015)}
FILES = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "prompts").glob("*.md"), *(ROOT / "templates").rglob("*.md"), *(ROOT / "deploy").rglob("*.md")]
PRIVATE = re.compile(r"(drive\.google\.com|docs\.google\.com|notion\.so|notion\.site|/Users/|/home/[a-z]+/|C:\\\\Users)")
LEFTOVER = re.compile(r"\b(ledgerlight|rainmaker|closeline|lighthouse|cortex|voiceprint)\b", re.I)
GITHUB = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+[^\s)>\]\"']*")
MARK = re.compile(r"<!--n:([\w.]+)-->(.*?)<!--/n-->")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def lookup(counts: dict, path: str):
    cur = counts
    for part in path.split("."):
        cur = cur[part]
    return cur


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    counts = json.loads((ROOT / "data" / "counts.json").read_text())
    bad: list[str] = []
    for f in sorted(set(FILES)):
        rel = f.relative_to(ROOT)
        text = f.read_text(encoding="utf-8")
        if any(d in text for d in DASHES):
            bad.append(f"{rel}: has an em or en dash")
        for m in PRIVATE.finditer(text):
            bad.append(f"{rel}: private path or link {m.group(0)!r}")
        for m in LEFTOVER.finditer(text):
            if rel.name not in ("CHANGELOG.md",):
                bad.append(f"{rel}: leftover word {m.group(0)!r}")
        for m in GITHUB.finditer(text):
            if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w-][\w.-]*", m.group(0)) or m.group(0).endswith(".git"):
                bad.append(f"{rel}: GitHub link must be the repo home page: {m.group(0)}")

        def repl(m: re.Match) -> str:
            try:
                want = str(lookup(counts, m.group(1)))
            except (KeyError, TypeError):
                bad.append(f"{rel}: unknown count {m.group(1)}")
                return m.group(0)
            if m.group(2) != want:
                if fix:
                    return f"<!--n:{m.group(1)}-->{want}<!--/n-->"
                bad.append(f"{rel}: {m.group(1)} says {m.group(2)}, measured {want}")
            return m.group(0)

        new = MARK.sub(repl, text)
        if fix and new != text:
            f.write_text(new, encoding="utf-8")
        for m in LINK.finditer(text):
            target = m.group(1)
            if re.match(r"[a-z]+:", target) or target.startswith("mailto"):
                continue
            if not (f.parent / unquote(target)).resolve().exists():
                bad.append(f"{rel}: broken link {target}")
    if bad:
        print("\n".join("PROBLEM " + b for b in bad))
        return 1
    print(f"OK {len(set(FILES))} documents checked")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
