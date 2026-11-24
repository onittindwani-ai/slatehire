# Go live checklist

Tick every line before you set `MODE=live` or put real applicants in.

1. [ ] [Business basics](02-BUSINESS-BASICS-CHECK.md) done, including the privacy notice and the retention period.
2. [ ] Hiring tool rules checked where you recruit (notice, bias audit, human review). Slatehire keeps a person in every decision, but that is not a legal opinion.
3. [ ] `DEMO_MODE=false`, a strong `SESSION_SECRET`, owner and approver password hashes set.
4. [ ] HTTPS in front of the web app and the API kept private.
5. [ ] Rubrics written by the hiring manager, read by one other person, then locked. Blind setting chosen on purpose.
6. [ ] Weights and words to look for reviewed for anything that could stand in for a protected trait (for example a school name or a gap in work).
7. [ ] `python3 tools/doctor.py --live` passes for every adapter you use. Test with one fake applicant first.
8. [ ] An offer was drafted, approved by a second person and written to a file, and you opened the file in your signing tool.
9. [ ] Backups run and one restore was tested ([operating](11-OPERATING-AND-BACKUPS.md)).
10. [ ] The kill switch was tested: turn it on and confirm that an invite is refused.
11. [ ] Everyone who scores or decides read [limits](14-LIMITS-AND-HONEST-NOTES.md).
