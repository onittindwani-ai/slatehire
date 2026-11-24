#!/usr/bin/env python3
"""Measure the numbers the docs quote and write them to data/counts.json.

Every count in README and docs/ comes from this file. Run it after any change, then run tools/check_docs.py.
  python3 tools/make_counts.py            measure and write (runs the Python tests once, with coverage)
  python3 tools/make_counts.py --fast     skip the test run and keep the last test and coverage numbers
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "counts.json"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable
sys.path.insert(0, str(ROOT / "apps/api/src"))


def run_tests() -> dict:
    cov = ROOT / ".coverage-counts.json"
    p = subprocess.run([PY, "-m", "pytest", "apps/api/tests", "mock/tests", "tools/tests", "-o", "addopts=", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "--cov=slatehire", f"--cov-report=json:{cov}"], cwd=ROOT, capture_output=True, text=True)
    m, sk, fl = (re.search(rf"(\d+) {w}", p.stdout) for w in ("passed", "skipped", "failed"))
    pct = None
    if cov.exists():
        pct = round(json.loads(cov.read_text())["totals"]["percent_covered"], 1)
        cov.unlink()
    return {"passed": int(m.group(1)) if m else 0, "skipped": int(sk.group(1)) if sk else 0, "failed": int(fl.group(1)) if fl else 0, "coverage_percent": pct}


def main(argv: list[str]) -> int:
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    sd, ev = ROOT / "data" / "seed", ROOT / "data" / "eval"
    rb = json.loads((sd / "rubrics.json").read_text())
    key = json.loads((sd / "answer_key.json").read_text())
    files = [p.suffix for p in (sd / "resumes").iterdir()]
    seed = {"applicants": len(key["resumes"]), "roles": len(rb), "criteria": sum(len(r["criteria"]) for r in rb.values()), "resumes_pdf": files.count(".pdf"), "resumes_text": files.count(".txt") + files.count(".md"),
            "twin_pairs": len(key["twins"]), "gap_pairs": len(key["gap_pairs"]), "injection_pairs": len(key["injection_pairs"]), "stuffing": len(key["stuffing"]), "non_traditional": len(key["non_traditional"]),
            "demographic_labels": len(json.loads((sd / "demographics.json").read_text())["groups"]), "inbox_emails": len(list((sd / "inbox").glob("*.eml"))),
            "heldout_leak_resumes": len(json.loads((ev / "heldout_leak.json").read_text())["resumes"]), "heldout_scoring_resumes": len(json.loads((ev / "heldout_scoring.json").read_text())["resumes"]),
            "heldout_fairness_cases": len(json.loads((ev / "heldout_fairness.json").read_text())["cases"]), "swap_identities": len(json.loads((ev / "swap_identities.json").read_text())["identities"])}
    lk, sc = json.loads((ev / "leak_first_run.json").read_text()), json.loads((ev / "scoring_first_run.json").read_text())
    evals = {"leak_first_run": {"planted": lk["known_name"]["planted"], "leaked": lk["known_name"]["leaked"], "rate_percent": round(100 * lk["known_name"]["leak_rate"], 1)},
             "scoring_first_run": {"resumes": sc["resumes"], "precision": sc["precision"], "recall": sc["recall"], "level_exact": sc["level_exact"], "level_within_one": sc["level_within_one"], "spearman": sc["rank_agreement_spearman"]["all"], "quotes": sc["quotes"]}}
    sys.path.insert(0, str(ROOT / "tools"))
    import eval_scoring  # noqa: E402

    now = eval_scoring.run()
    evals["scoring_now"] = {"precision": now["precision"], "recall": now["recall"], "level_exact": now["level_exact"], "level_within_one": now["level_within_one"], "spearman": now["rank_agreement_spearman"]["all"]}
    indep = {}
    for tag, fname in (("a_first", "set_a_first_run"), ("b_first", "set_b_first_run"), ("a_rerun", "set_a_rerun"), ("b_rerun", "set_b_rerun")):
        d = json.loads((ev / "independent" / f"{fname}.json").read_text())
        sc_, rd, fr = d["scoring"], d["redaction"]["name_unknown"], d["fairness"]
        indep[tag] = {"pairs": sc_["pairs"], "exact": sc_["exact"], "within_one": sc_["within_one"], "spearman": sc_["spearman_per_criterion"]["mean"], "quotes": sc_["evidence"]["quotes_shown"], "quotes_invalid": sc_["evidence"]["invalid"],
                      "not_found_share": sc_["no_evidence"]["reported_not_found"], "overclaims": sc_["no_evidence"]["overclaims_level_3_or_more"], "stuffed_exact": sc_["keyword_stuffed"]["exact"],
                      "inj_lines": sc_["instruction_injection"]["lines"], "inj_flagged": sc_["instruction_injection"]["lines_flagged"], "inj_quoted": sc_["instruction_injection"]["quotes_from_instruction_lines"],
                      "inj_rose": sc_["instruction_injection"]["totals_rose"], "probe_lines": sc_["probes"]["appended_instruction_lines"]["lines"], "probe_flagged": sc_["probes"]["appended_instruction_lines"]["lines_flagged"],
                      "probe_rose": sc_["probes"]["appended_instruction_lines"]["totals_rose"], "kw_probe_rose": sc_["probes"]["appended_keyword_line"]["totals_rose"], "resumes": sc_["resumes"],
                      "planted": rd["planted"], "leaked": rd["leaked"], "leak_percent": round(100 * rd["leak_rate"], 1), "fragments": rd["fragment_leaked"], "known_leaked": d["redaction"]["name_known"]["leaked"],
                      "keep": rd["keep_sentences"], "keep_lost": rd["keep_lost"], "fair_cases": fr["cases"], "fair_exact": fr["cases_exact"]}
    evals["independent"] = indep
    model = {"fixtures": len(list((ROOT / "data" / "llm_fixtures").glob("*.json"))), "tests": len(re.findall(r"^def test_", (ROOT / "apps/api/tests/test_model_path.py").read_text(), re.M)),
             "contract_tests": len(re.findall(r"^def test_", (ROOT / "mock/tests/test_contracts.py").read_text(), re.M)), "contract_vendors": len([d for d in (ROOT / "mock" / "contracts").iterdir() if d.is_dir()])}
    api = json.loads((ROOT / "docs" / "openapi.json").read_text())
    ops = sum(1 for vv in api["paths"].values() for k in vv if k in ("get", "post", "put", "patch", "delete"))
    tables = len(re.findall(r'__tablename__ = "cf_', (ROOT / "apps/api/src/slatehire/models.py").read_text()))
    adapters = len(re.findall(r"\badd\(", (ROOT / "apps/api/src/slatehire/registry.py").read_text()))
    lst = subprocess.run(["pnpm", "exec", "playwright", "test", "--list"], cwd=ROOT / "apps" / "web", capture_output=True, text=True).stdout
    mm = re.search(r"Total: (\d+) tests? in (\d+) files?", lst)
    e2e = {"tests": int(mm.group(1)), "files": int(mm.group(2))} if mm else old.get("e2e")
    scores = json.loads((ROOT / "data" / "tool_scores.json").read_text())
    pages = len(re.findall(r'id: "/', (ROOT / "apps/web/src/components/AppFrame.tsx").read_text())) + 1
    shots = len(list((ROOT / "docs" / "screenshots").glob("*.png")))
    tests = old.get("tests") if "--fast" in argv else run_tests()
    data = {"tables": tables, "api_paths": len(api["paths"]), "api_operations": ops, "adapters": adapters, "pages": pages, "screenshots": shots, "tool_groups": len(scores["groups"]), "tools_scored": sum(len(g["tools"]) for g in scores["groups"]),
            "seed": seed, "eval": evals, "model": model, "e2e": e2e, "tests": tests}
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    print("OK wrote", OUT.relative_to(ROOT), json.dumps({k: data[k] for k in ("tables", "api_paths", "adapters", "pages", "screenshots", "tools_scored", "tests")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
