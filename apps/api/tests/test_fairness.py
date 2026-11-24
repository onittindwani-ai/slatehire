import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from slatehire import fairness

CASES = json.loads((Path(__file__).resolve().parents[3] / "data/eval/heldout_fairness.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_hand_computed_case(case):
    rep = fairness.report({st: {g: tuple(v) for g, v in grp.items()} for st, grp in case["counts"].items()}, case["min_group"], F(case["threshold"]))
    for st, groups in case["expected"].items():
        for g, (rate, ratio, status) in groups.items():
            row = rep["stages"][st]["groups"][g]
            assert row["rate"] == F(rate), (st, g)
            assert row["status"] == status, (st, g, row)
            assert (row["ratio"] is None) if ratio is None else (row["ratio"] == F(ratio)), (st, g)
    for code in case.get("note_codes", []):
        assert code in rep["notes"]


def test_small_group_never_becomes_the_reference():
    r = fairness.step({"A": (40, 20), "B": (30, 15), "C": (6, 6)}, 10)
    assert r["reference"] == "A" and r["groups"]["C"]["status"] == "too_few" and r["groups"]["A"]["status"] == "reference"


def test_fisher_known_value():
    assert fairness.fisher_p(8, 2, 1, 5) == pytest.approx(0.0350, abs=1e-3)
