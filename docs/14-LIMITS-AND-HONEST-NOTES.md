# Limits and honest notes

## Not legal advice, and a person always decides
Hiring software is regulated in some places (for example notice and bias audit rules for automated tools, and anti discrimination law). Slatehire keeps a person in every decision and keeps a record, which helps, but it does not make you compliant. **Have a lawyer who knows employment and data rules where you hire review the use of this tool before the first real applicant** (notice to applicants, bias audit rules, human review, how long you keep records, the offer template). The fairness page says the same in its first line. The fairness page uses the four fifths rule as an indicator only ([facts](facts/four-fifths-rule.md)).

## What was measured, and how far to trust it
The same author wrote the scorer and the checks, so the numbers below are not an independent test. Held out means the resumes were made and set aside before the rules were tuned.
- Redaction leak, first run on <!--n:eval.leak_first_run.planted-->600<!--/n--> planted details: <!--n:eval.leak_first_run.leaked-->39<!--/n--> leaked (<!--n:eval.leak_first_run.rate_percent-->6.5<!--/n--> percent). They were fixed and the set then read 0 of 600, but that set is no longer held out. Over redaction was 0.
- Scoring, first run on <!--n:eval.scoring_first_run.resumes-->60<!--/n--> held out resumes: precision <!--n:eval.scoring_first_run.precision-->0.943<!--/n-->, recall <!--n:eval.scoring_first_run.recall-->0.947<!--/n-->, exact level match <!--n:eval.scoring_first_run.level_exact-->0.485<!--/n-->, within one level <!--n:eval.scoring_first_run.level_within_one-->0.854<!--/n-->, rank correlation <!--n:eval.scoring_first_run.spearman-->0.807<!--/n-->. All <!--n:eval.scoring_first_run.quotes-->348<!--/n--> quotes were real.
- All data is fictional. Nothing was tested on real applicants or real hiring outcomes.

## Known weaknesses
- The offline scorer is word and pattern rules. It misses meaning it has no words for, and it can be fooled by a resume stuffed with the right words: a skills line or a run of repeated keywords is counted as no evidence, but a stuffed line written as a sentence can still score.
- Redaction can leave small fragments. In one seed resume a stray quote and bracket stayed after a hidden email. Names hidden by pattern can still be inferred from context a person reads.
- Resume text is the only evidence. Gaps in work history and non traditional paths can be scored lower by criteria that reward a certain shape of career. Review the criteria for that.
- Group labels are voluntary and small groups are not compared.
- The model scorer (`SCORER=model` with `LLM_BACKEND=anthropic`) is real code behind the shared wrapper: one criterion per call, the redacted resume only, every quote found again by code, the total added up by code. It has only been run against a local fake server and recorded fixtures made from that fake server. It has NEVER run with a real key, so how a real model scores real resumes, and how well it agrees with a person, is UNVERIFIED. Test it on your own fictional resumes with the held out tool (`tools/eval_independent.py`) before it scores a real applicant, and keep the lawyer review recommendation below.
- The rules scorer on two independent sets (60 resumes each, written by people who never saw the code) agreed with the key on the exact level only about 4 times in 10 and within one level about 8 times in 10 (numbers in [evaluation](EVALUATION.md)). It scores low when a resume describes the work in words the rubric does not list. A vague mention is often read as no evidence. Use a score to read, never to rank or reject.
- Redaction without a known name left name fragments in a few resumes, and street addresses or school names in forms it has no pattern for. Reference people are redacted by a pattern for a line such as Reference: Name and for a References section, not by understanding the page.
- Approval and audit times come from the real clock, not the demo clock, so after +1 day a request can show an earlier date than the demo date at the top.
- Redaction can leave a place word (a town name) beside the [ADDRESS] tag.

## Never run live
No adapter was run against a real Ashby, Workable, Greenhouse, Cal.com, Google, mailbox or signing service. Docker, Vercel, Railway and Hetzner steps were not run. See [facts](FACTS-AND-SOURCES.md).

## Decided defaults (the implementer can change them)
Retention 365 days after a decline or withdrawal (hired people are never swept), smallest fairness group 10, the four fifths threshold, and at least 2 scorecards before an offer. These were decided for the shipped build on 2026-11-23. They are starting points, not legal advice: change them with the client's adviser, in the settings or the environment ([variables](04-ENVIRONMENT-VARIABLES.md)).
