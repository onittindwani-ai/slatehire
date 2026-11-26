# Slatehire spec

What it is: a hiring and onboarding pipeline for a small company. People apply, a rubric that a person locked is applied to the resume with identity hidden, the evidence is quoted word for word from the resume, a person decides every step, interviews use the same questions for everyone, scorecards are added up by code, an offer is drafted for a signing tool, and a 30, 60 and 90 day plan starts the new hire. A fairness indicator and an append only audit log sit beside all of it.

What it never does: reject anyone because of a score, guess a protected attribute, send an offer or an email to a candidate, write offer terms, or write to your ATS.

## Entities (tables start with cf_)

Role, Rubric (versions, a lock, a signature), Candidate (a neutral code such as A001), Application (stage and history), Resume (original text, redacted text, segments, where the flagged lines are, the language), Score (items with quotes, total, flags), Interview (kit, interviewers, time), Scorecard (one per interviewer, append only), Offer, OnboardingTask, Demographic (voluntary labels, read only by the fairness module), FairnessReport, IntakeLog, State. The base adds Approval, AuditEntry (hash chained), Event, Job and CostEntry.

## Pipeline

1. Role intake and a job post template (a person edits it).
2. Rubric: 2 to 10 criteria, each with a weight from 1 to 5, anchors for 1, 3 and 5, words to look for and an interview question. A person locks it. The signature (a fingerprint) covers the criteria, the blind setting and the redaction version. A locked rubric cannot change; a change is a new version that must be locked again.
3. Intake: paste, resume file, CSV, application email (IMAP), ATS pull (read only), signed webhook. Duplicates are skipped. The resume is redacted before anything else reads it.
4. Score under the locked rubric: input is the redacted text only. Every score has verbatim quotes and code checks that each quote is in the text. A score with a bad quote is rejected, so the evidence check is 100 percent by construction and is measured again over every stored score.
5. Shortlist, decline or withdraw: a person, with a written reason for declines. Needs a score under the locked rubric to shortlist.
6. Interviews: the kit is the same for everyone in the role. Scheduling is a calendar invite that needs live mode and a confirm. Scorecards are append only and hidden from the other interviewers until you send yours. Totals are arithmetic.
7. Offer: terms written by a person, a template body, approval by a second person, a file for the signing tool. Hired needs the handed off offer.
8. Onboarding: 30, 60 and 90 day plan from a template plus role lines. People tick tasks.
9. Fairness: selection rate per step by voluntary group, a four fifths indicator with exact fractions, a smallest group size, labelled as an indicator and not legal advice.
10. Retention: delete a person on request or after the retention period (not hired people).

## Blind mode

While an application is `applied` and the locked rubric has blind on, names, emails, phones and schools are hidden everywhere (list, board, workspace, interview names) and the server refuses to reveal them. After the shortlist decision identity is visible and a reveal is audited. The blind flag is part of the rubric signature, so changing it needs a new locked version.

## Safe by default

Draft mode sends nothing. A kill switch (owner) stops invites and file hand offs. Offers need a second person. The person who asked cannot approve their own request. The audit log is hash chained and the app refuses to edit or delete a row. Resumes are untrusted text: lines that talk to the scorer are flagged, never scored and never quoted. Every route needs a session except sign in and the signed application webhook. Rate limits on sign in and on all routes. SSRF guard on every address a person types.

## Adapters

ATS: seed (A), Ashby, Workable, Greenhouse (B, read only). Calendar: seed (A), Cal.com, Google Calendar (B). Mailbox: seed (A), IMAP (A, tested on a local mock server). Hand off: package file (A), Breezedoc (C: no live call built).

## Pages

Pipeline, Candidates (table), Candidate workspace, Roles and rubrics, Interviews, Offers, Onboarding, Fairness, Approvals, Audit log, Integrations.

## Evals

Redaction leak test and identity swap property, scoring against a held out labelled set, evidence quote validity (must be exactly 100 percent), score consistency, fairness arithmetic against hand computed cases. See `EVALUATION.md`.
