# Start here

Slatehire is a hiring and onboarding pipeline for a small company. It reads resumes with identity hidden, scores each one against a rubric that a person locked, shows the exact resume sentences behind every score, and then steps aside: a person decides every outcome.

## Who it is for
A founder, a hiring manager or an implementer who sets this up for a client. You should be able to follow a numbered guide and paste values into an environment file. You do not need to write code.

## What it does
- Takes applicants from a pasted resume, a resume file, a CSV, an application email box, a read only ATS pull, or a signed webhook.
- Hides names, emails, phones, addresses, schools, graduation years, pronouns and similar details before anything is scored.
- Scores 1 to 5 per criterion with word for word quotes. Code checks every quote is in the resume. A score with a bad quote is thrown away.
- Plans interviews with the same questions for everyone, collects structured scorecards, and adds them up by code.
- Drafts an offer from terms a person writes, asks a second person to approve, and writes a file for your signing tool.
- Starts a 30, 60 and 90 day plan for a new hire.
- Shows a fairness indicator and keeps an append only audit log.

## What it cannot do and will not do
- It never rejects anyone because of a score. Only a person moves an application, and a decline needs a written reason.
- It never guesses a protected attribute. Group labels for the fairness page are voluntary and kept apart.
- It never sends an email, an offer or a calendar invite on its own. An invite needs live mode and a confirm.
- It does not write offer terms.
- It is not legal advice. Hiring software is regulated in some places. See [fairness and legal notes](14-LIMITS-AND-HONEST-NOTES.md).
- The offline scorer is a set of rules, not a language model. It misses what it has no words for. A model scorer exists (`SCORER=model`) but has never run with a real key.

## Try it
[Quick demo](01-QUICK-DEMO.md): five minutes, no accounts. Repository home: https://github.com/onittindwani-ai/slatehire.
