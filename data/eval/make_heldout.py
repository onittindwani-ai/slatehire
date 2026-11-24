#!/usr/bin/env python3
"""Build the held out evaluation files. Run once, BEFORE the redaction and scoring code is written. The outputs are committed untouched.

  python3 data/eval/make_heldout.py

Writes: rubric_defs.json, swap_identities.json, heldout_leak.json (40 resumes with planted identity details), heldout_scoring.json (60 labelled resumes).
Everything is fictional. Names, schools, towns and employers are invented. Phone numbers use fictional ranges.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pools import CRITERIA, EMPLOYERS, FILLER, FIRST, LAST, ROLES, SCHOOLS, STATEMENTS, STREETS, TOWNS  # noqa: E402

OUT = Path(__file__).parent
SCHOOL_CORE = {"Ashgrove State College": "ashgrove", "Northmere Institute of Technology": "northmere", "Veldt University": "veldt", "Calder Bay Polytechnic": "calder", "University of Orrin Valley": "orrin", "Saltmarsh Academy": "saltmarsh", "Fenwick College of Commerce": "fenwick", "Harrowgate University": "harrowgate", "Institute of Applied Studies at Lowmere": "lowmere", "Tallis Heath College": "tallis"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
ACCENT = str.maketrans("eaio", "éáíó")


def identity(rng: random.Random, i: int) -> dict:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    sex = rng.choice(["he", "she"])
    y = rng.randint(1962, 1989)
    school = rng.choice(SCHOOLS)
    town = rng.choice(TOWNS)
    p3 = rng.randint(100, 199)
    return {"id": i, "first": first, "last": last, "full": f"{first} {last}", "sex": sex, "subj": sex, "obj": "him" if sex == "he" else "her", "poss": "his" if sex == "he" else "her",
            "title": rng.choice(["Mr", "Mrs", "Ms", "Miss"]) if sex == "she" else "Mr", "school": school, "town": town, "street": rng.choice(STREETS), "num": rng.randint(3, 299), "zip": f"0{rng.randint(1000, 9999)}",
            "pc": f"CV{rng.randint(1, 9)} {rng.randint(1, 9)}Z{rng.choice('ABKM')}", "email_local": f"{first}.{last}".lower().replace("-", "").replace(" ", ""), "phone10": f"5550100{p3 % 1000:03d}",
            "uk_phone": f"2079460{p3 % 1000:03d}", "handle": f"{first[0]}{last}".lower().replace("-", ""), "n": rng.randint(100, 9999), "birth_year": y, "birth_day": rng.randint(1, 28), "birth_month": rng.randint(1, 12),
            "age": 2026 - y, "grad_year": y + 22, "nat": "Corvalian"}


def fmt_phone(p: str, k: int) -> str:
    return [f"({p[:3]}) {p[3:6]}-{p[6:]}", f"{p[:3]}.{p[3:6]}.{p[6:]}", f"+1 {p[:3]} {p[3:6]} {p[6:]}", p, f"tel:+1{p}", "".join(chr(0xFF10 + int(c)) if c.isdigit() else c for c in f"{p[:3]}-{p[3:6]}-{p[6:]}")][k]


WORD = "zero one two three four five six seven eight nine".split()


def planted(id_: dict, rng: random.Random) -> list[dict]:
    I = id_
    f, l, F, L = I["first"], I["last"], I["first"].upper(), I["last"].upper()
    loc = I["email_local"]
    ph = I["phone10"]
    items: list[dict] = []

    def add(cat, where, text, cores, mode="norm"):
        items.append({"category": cat, "where": where, "text": text, "cores": cores, "mode": mode})

    # name (two items)
    name_opts = [("header", f"{f} {l}", [f, l]), ("header", f"{F} {L}", [f, l]), ("header", " ".join(f"{f}   {l}".upper()), [f, l]), ("header", f"{l}, {f}", [f, l]), ("header", f"{f[0]}. {l}", [l]),
                 ("footer", f"Page 1 of 2 | {f} {l} | Confidential", [f, l]), ("body", f"Sincerely, {f}", [f]), ("body", f"{f} is a dependable team member who enjoys steady work.", [f]),
                 ("header", f"Resume_{f}_{l}_2026.pdf", [f, l]), ("header", l.translate(ACCENT), [l]), ("footer", f"Prepared by {f} {l}", [f, l])]
    for w, t, c in rng.sample(name_opts, 2):
        add("name", w, t, c)
    em = [("header", f"{loc}@mail.example.test"), ("header", f"{loc} [at] mail [dot] example [dot] test"), ("header", f"{loc[:3]}​{loc[3:]}@mail.example.test"), ("header", f"Email: {loc}@\nmail.example.test"),
          ("header", f'<img src="logo.png" alt="Contact {loc}@mail.example.test">'), ("header", f"[write to me](mailto:{loc}@mail.example.test)"), ("header", f"{loc.upper()}@MAIL.EXAMPLE.TEST"), ("footer", f"{f.lower()}_{l.lower().replace('-', '')}(at)mail.example.test")]
    w, t = rng.choice(em)
    add("email", w, t, [loc.replace(".", "")])
    k = rng.randint(0, 6)
    if k == 5:
        add("phone", "header", f"+44 20 7946 0{I['uk_phone'][-3:]}", [f"79460{I['uk_phone'][-3:]}"])
    elif k == 6:
        add("phone", "header", "Phone: " + ", ".join(" ".join(WORD[int(c)] for c in g) for g in (ph[:3], ph[3:6], ph[6:])), ["".join(WORD[int(c)] for c in ph[:6])])
    else:
        add("phone", "header", f"Phone: {fmt_phone(ph, k)}", [ph])
    a = rng.choice([("header", f"{I['num']} {I['street']}, {I['town']}, ST {I['zip']}", [I["street"]]), ("header", f"Flat 3\n{I['num']} {I['street']}\n{I['town']} {I['pc']}", [I["street"]]),
                    ("header", f"PO Box {I['n']}, {I['town']}", [f"pobox{I['n']}"]), ("header", f"Apt 5B, {I['num']} {I['street']}", [I["street"]]), ("footer", f"Address: {I['num']} {I['street']} {I['town']} {I['zip']}", [I["street"]])])
    add("address", a[0], a[1], a[2])
    links = [f"linkedin.com/in/{f}-{l}-{I['n']}".lower(), f"https://www.linkedin.com/in/{I['handle']}", f"github.com/{I['handle']}", f"{I['handle']}.example.test", f"@{I['handle']}", f"instagram.com/{f}.{l[0]}".lower(), f"Portfolio: https://{f.lower()}.example.test/work", f"(in/{f}-{l})".lower()]
    for t in rng.sample(links, 2):
        core = f.lower() if f.lower() in t else I["handle"]
        add("link", "header", t, [core])
    ph_opts = [(f"![Photo of {f}](photo.jpg)", ["photo.jpg"]), ('<img src="headshot.png" alt="Headshot">', ["headshot.png"]), ("Photo: attached (headshot.jpg)", ["headshot.jpg"]), ("[image: portrait of applicant]", ["portraitofapplicant"]), ("Photograph enclosed", ["photographenclosed"])]
    t, c = rng.choice(ph_opts)
    add("photo", "header", t, c)
    y, d, m, age = I["birth_year"], I["birth_day"], I["birth_month"], I["age"]
    dob = [(f"Date of birth: {d} {MONTHS[m - 1]} {y}", [f"{d}{MONTHS[m - 1]}{y}".lower()]), (f"DOB {m:02d}/{d:02d}/{y}", [f"{m:02d}{d:02d}{y}"]), (f"Born {y} in {I['town']}", [f"born{y}"]), (f"Age: {age}", [f"age{age}"]),
           (f"{age} years old", [f"{age}yearsold"]), (f"Born on the {d}th of {MONTHS[m - 1]}, {y}", [f"{MONTHS[m - 1]}{y}".lower()]), (f"b. {y}", [f"b{y}"])]
    t, c = rng.choice(dob)
    add("dob_age", "header", t, c)
    g = I["grad_year"]
    gr = [(f"B.A. Economics, {g}", [str(g)]), (f"Class of {g}", [str(g)]), (f"Graduated in {g}", [str(g)]), (f"({g - 4} - {g})", [f"{g - 4}{g}"]), (f"Graduation: May {g}", [f"may{g}"])]
    t, c = rng.choice(gr)
    add("grad_year", "edu", t, c)
    sx = I["sex"]
    subj, poss = ("She", "her") if sx == "she" else ("He", "his")
    pr = [("header", f"({'she/her' if sx == 'she' else 'he/him'})", [f"{'sheher' if sx == 'she' else 'hehim'}"], "norm"), ("header", f"Pronouns: {'she/her' if sx == 'she' else 'he/him'}", [f"{'sheher' if sx == 'she' else 'hehim'}"], "norm"),
          ("body", f"{subj} has years of steady experience.", [subj.lower()], "token"), ("body", f"Led {poss} team of fifteen through two busy seasons.", [poss], "token"), ("header", "Pronouns: they/them", ["theythem"], "norm")]
    for w, t, c, mo in rng.sample(pr, 2):
        add("pronoun", w, t, c, mo)
    tt = rng.choice([("header", f"{I['title']}. {l}", [I["title"].lower()], "token"), ("body", "Previously worked as a Salesman in a retail shop.", ["salesman"], "token"), ("body", "Served as Chairwoman of the staff committee.", ["chairwoman"], "token"),
                     ("body", "Worked as a Foreman on the loading dock.", ["foreman"], "token"), ("body", "Began as a Waitress at a roadside diner.", ["waitress"], "token")])
    add("title", tt[0], tt[1], tt[2], tt[3])
    s = I["school"]
    core = SCHOOL_CORE[s]  # the distinctive word: a leak is this word surviving, not the whole name
    ins = [(f"{s}", [core]), (f"Alumna of {s}" if sx == "she" else f"Alumnus of {s}", [core]), (f"Studied at the {s}, with honours", [core])]
    if "University" in s and not s.startswith("University of"):
        ins.append((s.replace("University", "Univ."), [core]))
    t, c = rng.choice(ins)
    add("institution", "edu", t, c)
    per = rng.choice([("Marital status: married, two children", ["twochildren"]), (f"Nationality: {I['nat']}", ["corvalian"]), ("Gender: " + ("female" if sx == "she" else "male"), ["gender"]), ("Religion: Quaker", ["quaker"]), (f"Place of birth: {I['town']}", ["placeofbirth"]), ("Health: excellent", ["healthexcellent"])])
    add("personal", "header", per[0], per[1], "token" if per[1] == ["gender"] else "norm")
    return items


def compose(items: list[dict], bullets: list[str], rng: random.Random, layout: int, role_title: str) -> tuple[str, list[str]]:
    hd = [i["text"] for i in items if i["where"] == "header"]
    ed = [i["text"] for i in items if i["where"] == "edu"]
    bd = [i["text"] for i in items if i["where"] == "body"]
    ft = [i["text"] for i in items if i["where"] == "footer"]
    e1, e2 = rng.sample(EMPLOYERS, 2)
    keep = [e1, e2, role_title]
    H = (lambda s: f"## {s}") if layout == 1 else (lambda s: s.upper()) if layout == 0 else (lambda s: f"| {s} |")
    B = "* " if layout == 1 else "- " if layout == 0 else "| "
    half = len(bullets) // 2
    lines = hd + ["", H("Summary"), "Reliable and steady worker who likes clear goals. " + " ".join(bd), "", H("Experience"), f"{role_title}, {e1}, 2019 to 2026", *[B + b for b in bullets[:half + 1]], B + rng.choice(FILLER), "",
                  f"Assistant, {e2}, 2012 to 2019", *[B + b for b in bullets[half + 1:]], B + rng.choice(FILLER), "", H("Education"), *ed, "", *ft]
    return "\n".join(lines), keep


def main() -> None:
    rng = random.Random(20261123)
    # rubric definitions (no scoring terms yet: those are written later, after this file is committed)
    defs = {"roles": {k: {"title": v["title"], "criteria": [{"id": c, "name": CRITERIA[c][0], "topic": CRITERIA[c][1], "question": CRITERIA[c][2]} for c in v["criteria"]]} for k, v in ROLES.items()}}
    (OUT / "rubric_defs.json").write_text(json.dumps(defs, indent=1) + "\n")
    ids = [identity(random.Random(1000 + i), i) for i in range(60)]
    (OUT / "swap_identities.json").write_text(json.dumps({"note": "Fictional identities for the identity swap property test.", "identities": ids}, indent=1) + "\n")
    # leak set
    leak = []
    for n in range(40):
        ident = identity(random.Random(5000 + n), n)
        items = planted(ident, random.Random(7000 + n))
        role = list(ROLES)[n % 3]
        crit = ROLES[role]["criteria"]
        bullets = [STATEMENTS[c][rng.randint(2, 4)] for c in crit[:4]]
        text, keep = compose(items, bullets, rng, n % 3, ROLES[role]["title"])
        keep += [b[:40] for b in bullets]
        leak.append({"id": f"L{n + 1:02d}", "known_name": {"first": ident["first"], "last": ident["last"]}, "text": text, "planted": items, "keep": keep})
    (OUT / "heldout_leak.json").write_text(json.dumps({"note": "40 fictional resumes with planted identity details in unusual formats. mode norm: leak when a core string is found in the normalised redacted text; mode token: leak when the word is found as a whole word.", "resumes": leak}, indent=1, ensure_ascii=False) + "\n")
    # scoring set: 60 resumes, 20 per role, labels by construction
    weights = [0, 0, 0, 1, 1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 5, 5]
    rows = []
    for n in range(60):
        role = list(ROLES)[n % 3]
        crit = ROLES[role]["criteria"]
        labels = {c: rng.choice(weights) for c in crit}
        ident = identity(random.Random(9000 + n), n)
        bl = [STATEMENTS[c][labels[c] - 1] for c in crit if labels[c] > 0]
        rng.shuffle(bl)
        if not bl:
            bl = [FILLER[0]]
        head = [f"{ident['first']} {ident['last']}", f"{ident['email_local']}@mail.example.test", f"Phone: {fmt_phone(ident['phone10'], 0)}"]
        e1, e2 = rng.sample(EMPLOYERS, 2)
        h = len(bl) // 2
        text = "\n".join([*head, "", "SUMMARY", "Steady and reliable worker.", "", "EXPERIENCE", f"{ROLES[role]['title']}, {e1}, 2019 to 2026", *[f"- {b}" for b in bl[:h + 1]], f"- {rng.choice(FILLER)}", "", f"Assistant, {e2}, 2012 to 2019", *[f"- {b}" for b in bl[h + 1:]], f"- {rng.choice(FILLER)}",
                          "", "EDUCATION", f"B.A., {ident['school']}, {ident['grad_year']}"])
        rows.append({"id": f"S{n + 1:02d}", "role": role, "known_name": {"first": ident["first"], "last": ident["last"]}, "text": text, "labels": labels, "label_note": "level 0 means the criterion is not shown; 1 to 5 as written by the author"})
    (OUT / "heldout_scoring.json").write_text(json.dumps({"note": "60 labelled fictional resumes. Labels are the level of the statement the author wrote into the resume, by construction. Same author as the rules: not independent.", "resumes": rows}, indent=1) + "\n")
    print("wrote", len(leak), "leak resumes with", sum(len(r["planted"]) for r in leak), "planted items;", len(rows), "scoring resumes")


if __name__ == "__main__":
    main()
