# Design notes

Written before any CSS of Slatehire, as the quality gates ask. Everything here is original to this repo.

## What Slatehire feels like
A fair, calm hiring desk. The person making the decision should feel that nothing is hiding behind a number: every score has the resume sentence it came from underneath it, identity is out of the way until it is needed, and every consequential button asks for a reason in plain words. The accent is rose, a muted dusty pink red that reads as warm and human. True red stays for real alarms only (a rejected quote, a tampered signature, the kill switch).

## Palette (60, 30, 10)
60 percent warm neutrals from the kit (cream, oat). 30 percent coffee ink and borders. 10 percent rose for the one action on a screen, the active navigation row, the evidence highlight and the blind switch when it is on. Evidence highlights use rose tints at three strengths so overlapping criteria stay readable; they are never the only signal (each highlight also carries an underline and a criterion label). Stage colours are not used: a stage is its column and its label. Contrast is checked by the kit test and by axe in both themes.

## Type and spacing
Geist for the interface and numbers, Instrument Serif for page titles and the big total on a candidate. The resume is set in the interface font at 16 px, line height 1.6 and a 65 character measure, because the person reads it closely. Spacing 8, 13, 21, 34, 55, 89. The candidate workspace splits 61.8 to 38.2: the resume on the left, the score and the actions on the right. On a phone the score moves below the resume.

## Signature: the resume with evidence and the blind switch
The resume is shown with identity pieces as small grey tags ([NAME], [SCHOOL]) while blind mode is on. Where a score quotes the resume, the exact words are marked. Hovering or focusing a criterion row in the score table marks only that criterion's quotes and scrolls the first one into view. A switch in the header turns the redacted view on and off for people who are allowed to see identity (after the shortlist); while the role's rubric enforces blind, the switch is on, disabled and says why. When identity is shown, the tags flip to the original words with a short 160 ms cross fade; reduced motion makes it instant. Every reveal is written to the audit log by the server, not by the page.

## Micro interactions (from the shared catalogue)
Every button presses, shows a spinner and then a tick. Totals count up. Cards on the board lift on drag, a gap opens and the card settles on drop; a toast offers Undo for eight seconds. A move needing a reason opens a small dialog with the reason field focused, a character counter and the rule in words. The rubric builder shows weights as a stacked bar that resizes as numbers change and a live list of what would stop a lock. Scorecards use five tap targets per criterion and show nothing about other interviewers until you send. Skeletons match their final layout. Empty states always name the next step. Errors say what happened and how to fix it. Copy buttons turn into a tick.

## Motion
Tokens from the kit: out easing for entrances, press 120 to 160 ms, popovers 180 to 240 ms, sheets 240 to 320 ms, charts 600 to 800 ms once. Only transform and opacity animate. Reduced motion keeps fades and removes movement.

## Fairness page wording
The page opens with one line: this is an indicator for a person to look at, not a finding and not legal advice. Groups under the smallest size are shown with their counts and a grey "too few to say", never a ratio. A flagged group uses the warning tone with the text "below four fifths of the highest rate", not the danger tone, because a flag is a question to ask, not a verdict.

## What is not in the base and is built here
Resume viewer with evidence marks, score table, board card, rubric editor, scorecard form, stage reason dialog, fairness table. Each is a small component in `apps/web/src/components`. Saved table views and column resize are not built (listed as not in base 1.1.1).
