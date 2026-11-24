#!/usr/bin/env python3
"""Measure the offline scorer on the held out labelled set (data/eval/heldout_scoring.json): 60 resumes, labels written with the resumes.

  python3 tools/eval_scoring.py          print the numbers
  python3 tools/eval_scoring.py --save   save data/eval/scoring_first_run.json (refuses to overwrite)

The scorer is a set of rules, NOT a language model. The labels and the rules have the same author, so this is not an independent test.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
from slatehire.redaction import redact  # noqa: E402
from slatehire.scoring import score_resume  # noqa: E402

FIRST = ROOT / "data" / "eval" / "scoring_first_run.json"


def ranks(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return round(num / den, 3) if den else 0.0


def run() -> dict:
    rb = json.loads((ROOT / "data/seed/rubrics.json").read_text())
    rows = json.loads((ROOT / "data/eval/heldout_scoring.json").read_text())["resumes"]
    tp = fp = fn = tn = exact = near = both = 0
    per_level: dict[int, list[int]] = {}
    by_role: dict[str, tuple[list, list]] = {}
    quotes = bad_quotes = 0
    for r in rows:
        crit = rb[r["role"]]["criteria"]
        red = redact(r["text"], [r["known_name"]["first"], r["known_name"]["last"]]).redacted
        res = score_resume(crit, red)
        got, lab = [], []
        for c, it in zip(crit, res["items"]):
            L = r["labels"][c["id"]]
            v = it["value"] or 0
            quotes += len(it["quotes"])
            bad_quotes += it["state"] == "rejected"
            if L and v:
                tp += 1; both += 1; exact += v == L; near += abs(v - L) <= 1
                per_level.setdefault(L, []).append(v)
            elif L:
                fn += 1
            elif v:
                fp += 1
            else:
                tn += 1
            got.append(c["weight"] * v); lab.append(c["weight"] * L)
        g, l = by_role.setdefault(r["role"], ([], []))
        g.append(sum(got)); l.append(sum(lab))
    allg = [x for g, _ in by_role.values() for x in g]
    alll = [x for _, l in by_role.values() for x in l]
    return {"resumes": len(rows), "criteria_checked": tp + fp + fn + tn, "found_correctly": tp, "found_wrongly": fp, "missed": fn, "correctly_absent": tn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None, "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "level_exact": round(exact / both, 3) if both else None, "level_within_one": round(near / both, 3) if both else None, "levels_compared": both,
            "mean_score_by_label": {str(k): round(sum(v) / len(v), 2) for k, v in sorted(per_level.items())},
            "rank_agreement_spearman": {"all": spearman(allg, alll), **{k: spearman(g, l) for k, (g, l) in by_role.items()}}, "rejected_scores": bad_quotes, "quotes": quotes}


def main(argv: list[str]) -> int:
    res = {"note": "Held out set, first run, saved untouched. Rules scorer, not a language model. Same author as the rules: not independent.", **run()}
    print(json.dumps({k: v for k, v in res.items() if k != "note"}, indent=1))
    if "--save" in argv:
        if FIRST.exists():
            print("refusing: the first run is already saved")
            return 1
        FIRST.write_text(json.dumps(res, indent=1) + "\n")
        print("saved", FIRST.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
