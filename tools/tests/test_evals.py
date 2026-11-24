"""Floors for the held out measurements. The first runs are saved untouched in data/eval/*_first_run.json; these tests guard the numbers after the fixes."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "apps/api/src"), str(ROOT)]

import eval_redaction  # noqa: E402
import eval_scoring  # noqa: E402


def test_redaction_leaks_nothing_in_either_mode_and_keeps_the_words_that_matter():
    for known in (True, False):
        r = eval_redaction.run(known)
        assert r["planted"] == 600 and r["leaked"] == 0 and r["must_keep_lost"] == 0, (known, r["leaked"])


def test_first_runs_are_saved_and_honest():
    leak = json.loads((ROOT / "data/eval/leak_first_run.json").read_text())
    assert leak["known_name"]["leaked"] == 39 and leak["known_name"]["planted"] == 600
    sc = json.loads((ROOT / "data/eval/scoring_first_run.json").read_text())
    assert sc["resumes"] == 60 and sc["rejected_scores"] == 0 and 0.4 < sc["level_exact"] < 0.6


def test_scoring_agreement_with_the_human_labels_stays_above_the_floor():
    r = eval_scoring.run()
    assert r["rejected_scores"] == 0 and r["precision"] >= 0.9 and r["recall"] >= 0.9 and r["level_within_one"] >= 0.8 and r["rank_agreement_spearman"]["all"] >= 0.75
