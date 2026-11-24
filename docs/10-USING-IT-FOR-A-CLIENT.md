# Using it for a client

One copy of Slatehire serves one client. One repository clone, one database, one set of variables, one set of logins. Never share a database between two clients: the blind view and the roles separate people inside one company, not one company from another.

## What you are selling

Setup, a trial period in draft mode, a short training for the people who decide, and a monthly check. You are selling a hiring process that is written down: a rubric agreed before anyone is read, evidence quotes you can check against the resume, a blind first look, a person who makes every decision, a second person for every offer, and a record of all of it. You are not selling better hires, faster hiring or a legal opinion, and you should say so plainly. Nothing here was measured on real hiring outcomes, and the demo applicants are fictional. Slatehire never rejects, moves or hires anyone by itself, and it never sends an offer to a candidate.

## What to charge for

This guide gives no price figures. It gives the shape of the offer so you can price it after looking at your market and your costs.

- **Setup, once.** The business basics check (`02`), a fresh copy for this client, writing the rubrics with the hiring managers (criteria, weights and what a 1, a 3 and a 5 look like), connecting the mailbox or the applicant tracker read only, drafting the applicant notice with the client's adviser, setting the logins, and a trial period in draft mode. Charge for your hours and your care, not for the software, which is free.
- **Training, once.** An hour or two with the people who decide: how to read an evidence mark, what the score is not, how scorecards stay hidden until you send yours, how a decline needs a written reason.
- **Running it, monthly.** A short review: the fairness page read together, the retention sweep and what it removed, the rubrics that need a new locked version, the updates (`12`) and the backup check (`11`). State plainly how many hours a month that includes.
- **Costs that pass through, at cost.** Hosting, the applicant tracker or mailbox plan, the calendar tool and any model usage. Show these as the client's own accounts, not as your markup.
- **Never charge for** a promised number of hires, a promised time to hire, a promised score, or a claim that the tool removes bias. It does not, and the fairness page is an indicator, not a finding.

## Get a legal review before the first real applicant

Hiring tools are regulated in some places. Depending on where the client recruits and where the applicants live, rules can require notice to applicants, a bias audit of the tool, a way to ask for a human review, limits on what is stored and for how long, and equal treatment checks. The rules differ by country, state and city, and they change. Slatehire keeps a person in every decision and keeps a record, which helps, but it does not make anyone compliant, and the fairness page is an indicator and not a legal test.

So recommend, in writing, that the client has a lawyer who knows employment and data rules where they hire review the use of the tool before the first real applicant: the notice text, the retention period, the way scores are used, and the offer template. Put that recommendation in the contract (below) and keep a copy of the answer. This is not legal advice from you or from this guide.

## Onboarding checklist

1. Run `02-BUSINESS-BASICS-CHECK.md` with the client: who employs, what notice applicants get, where they recruit, how long records are kept.
2. Make a fresh copy for this client with `DEMO_MODE=false`, their company name, their own owner login (`tools/hash_password.py`) and their own `SESSION_SECRET`.
3. Agree who decides. The owner moves people and may show identity after the shortlist. A second person approves every offer (the approver login). A read only login (`VIEWER_EMAIL`) suits a manager who only looks. Interviewers sign in as approvers so they can send scorecards. Write down who has which login.
4. Ask for two or three real job posts and the criteria the managers really use. Turn them into rubrics with anchors for 1, 3 and 5. Check them for criteria that reward only one shape of career.
5. Run the demo with the client so they see blind mode and the evidence marks (`01`).
6. Set the hiring rules in `04`. The decided defaults are: keep a declined or withdrawn applicant 365 days, compare groups only when each has at least 10 people, the four fifths threshold on the fairness page, and at least 2 scorecards before an offer. Change any of them with the client's adviser and write the choice down.
7. Connect the mailbox or the applicant tracker read only (`03`). Test with a fake applicant you made up.
8. Lock the rubrics together. Explain that a change after the lock means a new locked version, and that earlier scores keep the version they used.
9. Walk through one full path with made up people: shortlist, interview, scorecards, offer file, onboarding plan.
10. Run in draft mode for at least two weeks. Read a sample of scores against the resumes yourself and count where a score looks wrong.
11. Follow `09-GO-LIVE-CHECKLIST.md`.

## Handover

- Give the client their own owner login and approver login, then remove yours.
- Hand over the backup steps (`11`), the name of the person who updates the app (`12`) and the retention setting with the reason for it.
- Hand over secrets inside the client's own hosting account, never by chat or email.
- Show the kill switch (Pause all), the audit check and the fairness page, and say what each one does and does not prove.
- Tell them what is UNVERIFIED in [limits](14-LIMITS-AND-HONEST-NOTES.md). Keep no copy of their applicant data.
- Agree who answers when Slatehire gets something wrong. A score will sometimes be wrong, which is why a person decides.

## What to put in the client contract

Plain wording, checked by your own lawyer: what setup and the monthly work include; that the client owns the data, the accounts and the decisions; that third party accounts and their costs belong to the client; that Slatehire proposes and a person decides, with no promised results, no promised time to hire and no promise that it removes bias; that the client has been told to get a legal review of the tool where they recruit, and has agreed to do so (or has declined in writing); that the client gives applicants the notice that the law where they live requires; how long applicant data is kept and who can read it; who is responsible for the answers to access and deletion requests; that the offer file is a template that needs the client's own review before anyone signs; what happens to the data and the copy when the contract ends; and that you make no legal, tax or employment advice claim.

## Keep it honest

The scorer in the demo is a set of rules and not a language model (a model scorer is built but has never run with a real key), and its measured scores are in [EVALUATION.md](EVALUATION.md), with the misses. It was tested on fictional resumes only. Say that to the client before they trust a number.
