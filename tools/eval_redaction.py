#!/usr/bin/env python3
"""Measure identity redaction on the held out leak set (data/eval/heldout_leak.json).

  python3 tools/eval_redaction.py            print the numbers
  python3 tools/eval_redaction.py --save     save data/eval/leak_first_run.json (refuses to overwrite: the first run is kept untouched)

Two modes: the candidate name is known from the application form, and the name is not known (the redactor must find it in the text).
A leak is a planted identity detail still readable in the redacted text. Over redaction is the share of words that must survive and did not.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
from slatehire.redaction import redact  # noqa: E402

DATA = ROOT / "data" / "eval" / "heldout_leak.json"
FIRST = ROOT / "data" / "eval" / "leak_first_run.json"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", s))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s.lower() if not unicodedata.combining(c)))


def leaked(item: dict, redacted: str) -> bool:
    if item["mode"] == "token":
        low = redacted.lower()
        return any(re.search(rf"(?<![a-z]){re.escape(c.lower())}(?![a-z])", low) for c in item["cores"])
    n = norm(redacted)
    folded = re.sub(r"[^a-z0-9]+", " ", "".join(c for c in unicodedata.normalize("NFKD", redacted.lower()) if not unicodedata.combining(c)))
    # a short core (under 6 characters) is matched as a whole word, because glued up it can appear across word boundaries ("needed data" holds "edda")
    return any((norm(c) in n) if len(norm(c)) >= 6 else bool(re.search(rf"(?<![a-z0-9]){re.escape(norm(c))}(?![a-z0-9])", folded)) for c in item["cores"])


def run(known: bool) -> dict:
    rows = json.loads(DATA.read_text())["resumes"]
    per: dict[str, dict] = {}
    keep_total = keep_lost = 0
    missed: list[dict] = []
    for r in rows:
        names = [r["known_name"]["first"], r["known_name"]["last"]] if known else None
        out = redact(r["text"], known_names=names).redacted
        for it in r["planted"]:
            c = per.setdefault(it["category"], {"planted": 0, "leaked": 0})
            c["planted"] += 1
            if leaked(it, out):
                c["leaked"] += 1
                missed.append({"resume": r["id"], "category": it["category"], "text": it["text"]})
        for k in r["keep"]:
            keep_total += 1
            keep_lost += k not in out
    tot = sum(c["planted"] for c in per.values())
    lk = sum(c["leaked"] for c in per.values())
    for c in per.values():
        c["leak_rate"] = round(c["leaked"] / c["planted"], 3)
    return {"name_known": known, "planted": tot, "leaked": lk, "leak_rate": round(lk / tot, 3), "per_category": per, "must_keep_phrases": keep_total, "must_keep_lost": keep_lost, "over_redaction_rate": round(keep_lost / keep_total, 3), "missed": missed}


def main(argv: list[str]) -> int:
    res = {"note": "Held out leak set, first run, saved untouched. Same author as the redactor, so not independent.", "known_name": run(True), "unknown_name": run(False)}
    for k in ("known_name", "unknown_name"):
        r = res[k]
        print(f"{k}: planted {r['planted']}, leaked {r['leaked']} ({r['leak_rate']:.1%}), over redaction {r['over_redaction_rate']:.1%}")
        for cat, c in sorted(r["per_category"].items()):
            print(f"   {cat:12s} {c['leaked']:3d} of {c['planted']:3d} leaked")
    if "--save" in argv:
        if FIRST.exists():
            print("refusing: the first run is already saved")
            return 1
        FIRST.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
        print("saved", FIRST.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
