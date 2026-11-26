"""Load the fictional demo company. 90 applicants for three roles, a locked rubric each, voluntary labels, and a pipeline already moved by people:
shortlists, declines with reasons, interviews with scorecards, one offer waiting for approval and one hire with an onboarding plan.

Every decision below is made by calling the same functions the API uses, as a named person, so the demo obeys the same rules as a real install.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire import fairness_service, intake, interviews, offers, onboarding, pipeline, rubric_service, scoring_service
from slatehire.ingest import Applicant, text_from_bytes
from slatehire.models import Application, Candidate, Interview, Offer, Role, Scorecard
from sendora_core.approvals import decide, request_approval

OWNER = "owner@example.test"
APPROVER = "approver@example.test"
INTERVIEWERS = ["iris.wells@example.test", "jonas.okafor@example.test"]


def _read(seed: Path, rel: str):
    return json.loads((seed / rel).read_text())


def load_world(s: Session, ctx) -> dict:
    seed = Path(ctx.settings.seed_dir) / "seed"
    now = ctx.now(s)
    rb, key = _read(seed, "rubrics.json"), _read(seed, "answer_key.json")["resumes"]
    roles: dict[str, Role] = {}
    for rk, r in rb.items():
        role = rubric_service.create_role(s, OWNER, r["title"], "Demo company", f"A fictional {r['title'].lower()} role for the demo.", key=rk)
        rub = rubric_service.new_draft(s, role, OWNER, r["criteria"], True)
        rubric_service.lock(s, rub, OWNER, now)
        role.job_post = rubric_service.job_post_draft(role, r["criteria"])
        roles[rk] = role
    rows = list(__import__("csv").DictReader((seed / "applicants.csv").open(encoding="utf-8")))
    apps: dict[str, Application] = {}
    for row in rows:
        data = (seed / "resumes" / row["resume_file"]).read_bytes()
        a = Applicant(row["name"], row["email"], row["phone"], row["role"], text_from_bytes(data, row["resume_file"]), row["resume_file"], row["source"], row["school"])
        app, _ = intake.add_applicant(s, a, roles[row["role"]], "intake", now, code=row["code"], settings=ctx.settings)
        apps[row["code"]] = app
    s.flush()
    labels = _read(seed, "demographics.json")["groups"]
    fairness_service.set_labels(s, {c: l for c, l in labels.items() if l != "undisclosed"}, OWNER)
    scorer = ctx.scorer(s)
    for app in apps.values():
        scoring_service.score_application(s, app, "scorer", now, scorer)
    s.flush()
    state = _stage_pipeline(s, ctx, roles, apps, key, now)
    s.flush()
    return {"roles": len(roles), "applicants": len(apps), **state}


def _top(s: Session, role: Role, apps: dict[str, Application]) -> list[Application]:
    rub = rubric_service.latest(s, role.id, locked_only=True)
    mine = [a for a in apps.values() if a.role_id == role.id]
    return sorted(mine, key=lambda a: (-scoring_service.latest_score(s, a.id, rub.id).total, a.id))


def _stage_pipeline(s: Session, ctx, roles, apps, key, now) -> dict:
    st = ctx.settings
    counts = {"shortlisted": 0, "declined": 0, "interviews": 0, "scorecards": 0}
    cards: dict[str, list[Application]] = {}
    for rk, role in roles.items():
        ranked = _top(s, role, apps)
        for a in ranked[:7]:
            pipeline.move(s, a, "shortlisted", OWNER, "Strong evidence on the heavier criteria.", now, st)
            counts["shortlisted"] += 1
        for a in ranked[-4:]:
            pipeline.move(s, a, "declined", OWNER, "Little evidence of the main criteria for this role.", now, st)
            counts["declined"] += 1
        cards[rk] = ranked[:4]
        for a in ranked[:3]:
            iv = interviews.plan(s, a, OWNER, INTERVIEWERS, now + timedelta(days=3, hours=2), 45, "structured", now)
            a.history = [*a.history]  # plan() moves nothing; the move to interviewing is a person's call
            pipeline.move(s, a, "interviewing", OWNER, "Interview planned.", now, st)
            counts["interviews"] += 1
            if a in ranked[:2]:
                _cards(s, iv, key, a, now, spread=(rk == "ops" and a is ranked[0]))
                counts["scorecards"] += 2
    # one offer waiting for a second person, one hire with an onboarding plan
    sup, ops = cards["support"][0], cards["ops"][1]
    o1 = offers.create(s, sup, OWNER, "Customer Support Specialist", (ctx.today(s) + timedelta(days=40)).isoformat(), "Full time, base pay as agreed in the interview, review after 6 months. [Demo terms, fictional.]", ctx.today(s), st.min_scorecards, st.company_name)
    offers.ask_approval(s, o1, OWNER)
    o2 = offers.create(s, ops, OWNER, "Operations Coordinator", (ctx.today(s) + timedelta(days=30)).isoformat(), "Full time, base pay as agreed in the interview, review after 6 months. [Demo terms, fictional.]", ctx.today(s), st.min_scorecards, st.company_name)
    offers.ask_approval(s, o2, OWNER)
    decide(s, o2.approval_id, True, APPROVER, "approver", "Terms match the interview notes.")
    o2.status = "approved"
    offers.hand_off(s, ctx, o2, OWNER)
    pipeline.move(s, ops, "hired", OWNER, "Signed offer received.", now, st)
    onboarding.create_plan(s, ops, OWNER, date.fromisoformat(o2.start_date))
    return {**counts, "offers": 2, "hired": 1}


def _cards(s: Session, iv: Interview, key: dict, app: Application, now, spread: bool) -> None:
    from slatehire.models import Candidate

    code = s.get(Candidate, app.candidate_id).code
    lv = key.get(code, {}).get("levels", {})
    first: dict[str, int] = {}
    for n, who in enumerate(INTERVIEWERS):
        ratings = {}
        for j, k in enumerate(iv.kit):
            base = max(1, min(5, int(lv.get(k["criterion_id"], 0)) or 2))
            r = max(1, min(5, base + (-1 if n else 0)))
            if n and spread and j == 0:
                r = 5 if first[k["criterion_id"]] <= 3 else 1  # a planted disagreement of two points or more
            ratings[k["criterion_id"]] = r
        first = ratings if n == 0 else first
        interviews.submit_scorecard(s, iv, who, ratings, {iv.kit[0]["criterion_id"]: "Gave a clear example with a number."}, "yes" if sum(ratings.values()) / len(ratings) >= 3 else "no", now)
