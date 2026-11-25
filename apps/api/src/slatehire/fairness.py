"""Fairness indicator. Pure arithmetic on counts, in exact fractions. An INDICATOR for a person to look at, never a finding of discrimination and never legal advice.

Selection rate at a step = people selected at that step / people who entered that step (the step conversion). The impact ratio of a
group = its rate / the highest rate among groups big enough to compare. A group is flagged when its ratio is below the threshold
(default four fifths, as in the US Uniform Guidelines, 29 CFR 1607.4 D); a ratio exactly at the threshold is not flagged. A group whose
entering count is below `min_group` is "too few to say": it is neither a reference nor compared. The arithmetic keeps its counts, but `to_json` (what is saved and shown) blanks them:
a group that small is a handful of people, and its counts would say what happened to each of them.
Demographic data enters ONLY here. No scoring, redaction or interview code imports this module or reads that data.
"""

from __future__ import annotations

from fractions import Fraction

STAGES = ("shortlisted", "interviewed", "offered", "hired")
UNDISCLOSED = "undisclosed"
THRESHOLD = Fraction(4, 5)


def fisher_p(a: int, b: int, c: int, d: int) -> float:
    """Two sided Fisher exact p value for [[a, b], [c, d]] (a selected and b not selected in group 1, c and d in group 2)."""
    from math import comb

    n1, n2, k = a + b, c + d, a + c
    tot = comb(n1 + n2, k)
    lo, hi = max(0, k - n2), min(k, n1)
    p0 = comb(n1, a) * comb(n2, c) / tot
    return min(1.0, sum(comb(n1, x) * comb(n2, k - x) / tot for x in range(lo, hi + 1) if comb(n1, x) * comb(n2, k - x) / tot <= p0 * (1 + 1e-9)))


def step(groups: dict[str, tuple[int, int]], min_group: int = 10, threshold: Fraction = THRESHOLD) -> dict:
    """groups: name -> (entered, selected). Returns rows by group plus the notes."""
    rates = {g: (Fraction(sel, den) if den else Fraction(0)) for g, (den, sel) in groups.items()}
    eligible = [g for g, (den, _s) in groups.items() if den >= min_group and g != UNDISCLOSED]
    top = max((rates[g] for g in eligible), default=Fraction(0))
    ref = min((g for g in eligible if rates[g] == top), default=None)
    rows, notes = {}, []
    for g, (den, sel) in sorted(groups.items()):
        row = {"entered": den, "selected": sel, "rate": rates[g], "ratio": None, "status": "", "p_value": None}
        if g == UNDISCLOSED:
            row["status"] = "undisclosed"
        elif g not in eligible:
            row["status"] = "too_few"
        elif top == 0:
            row["status"] = "not_computable"
        else:
            row["ratio"] = rates[g] / top
            row["status"] = "reference" if g == ref else ("flagged" if row["ratio"] < threshold else "ok")
            if g != ref and ref is not None:
                rd, rs = groups[ref]
                row["p_value"] = round(fisher_p(sel, den - sel, rs, rd - rs), 4)
        rows[g] = row
    if len(eligible) == 1:
        notes.append("no_comparison")
    if not eligible:
        notes.append("no_group_big_enough")
    if eligible and top == 0:
        notes.append("nobody_selected")
    return {"groups": rows, "notes": notes, "reference": ref}


def report(counts: dict[str, dict[str, tuple[int, int]]], min_group: int = 10, threshold: Fraction = THRESHOLD) -> dict:
    out = {"stages": {st: step({g: tuple(v) for g, v in grp.items()}, min_group, threshold) for st, grp in counts.items()}, "min_group": min_group, "threshold": threshold}
    out["flagged"] = [[st, g] for st, r in out["stages"].items() for g, row in r["groups"].items() if row["status"] == "flagged"]
    out["notes"] = sorted({n for r in out["stages"].values() for n in r["notes"]})
    return out


def to_json(rep: dict) -> dict:
    """Fractions as strings and as decimals, ready for the API."""
    def cell(row: dict) -> dict:
        if row["status"] == "too_few":
            return {**row, "entered": None, "selected": None, "rate": None, "rate_pct": None, "ratio": None, "ratio_dec": None, "p_value": None, "fewer_than": rep["min_group"]}
        return {**row, "rate": str(row["rate"]), "rate_pct": round(float(row["rate"]) * 100, 1), "ratio": None if row["ratio"] is None else str(row["ratio"]), "ratio_dec": None if row["ratio"] is None else round(float(row["ratio"]), 3)}
    return {"min_group": rep["min_group"], "threshold": str(rep["threshold"]), "flagged": rep["flagged"], "notes": rep["notes"],
            "stages": {st: {"reference": r["reference"], "notes": r["notes"], "groups": {g: cell(row) for g, row in r["groups"].items()}} for st, r in rep["stages"].items()},
            "disclaimer": "This is an indicator for a person to look at. It is not a finding of discrimination and it is not legal advice."}
