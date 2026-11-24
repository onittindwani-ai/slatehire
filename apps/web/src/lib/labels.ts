/** Plain words for names the server uses inside. One place, so no screen shows a raw name like application.shortlisted. */

const AUDIT_ACTION: Record<string, string> = {
  "applicant.added": "Applicant added", "application.shortlisted": "Moved to Shortlisted", "application.interviewing": "Moved to Interviewing", "application.offer": "Moved to Offer", "application.hired": "Marked hired",
  "application.declined": "Declined", "application.withdrawn": "Withdrawn", "score.created": "Scored under the locked rubric", "identity.revealed": "Identity shown",
  "role.created": "Role created", "role.edited": "Role edited", "rubric.drafted": "Rubric draft started", "rubric.edited": "Rubric draft edited", "rubric.locked": "Rubric locked",
  "interview.planned": "Interview planned", "interview.invited": "Calendar invite recorded", "scorecard.sent": "Scorecard sent",
  "offer.drafted": "Offer drafted", "offer.approved": "Offer approved", "offer.rejected": "Offer rejected", "offer.handed_off": "Offer file written", "offer.withdrawn": "Offer withdrawn",
  "approval.requested": "Approval asked for", "approval.approved": "Approved", "approval.rejected": "Rejected",
  "onboarding.planned": "Onboarding plan made", "onboarding.task_added": "Onboarding task added", "onboarding.task_done": "Onboarding task ticked off", "onboarding.task_reopened": "Onboarding task reopened",
  "candidate.deleted": "Personal data deleted", "fairness.report": "Fairness report run", "fairness.labels_set": "Voluntary labels imported",
  "settings.kill_switch": "Kill switch changed", "settings.force_draft": "Draft mode changed", "demo.stress": "Demo rows added", "demo.reset": "Demo data reset",
};
export const auditAction = (a: string) => AUDIT_ACTION[a] ?? a.replace(/[._]/g, " ").replace(/^./, (c) => c.toUpperCase());
/** "application:31" as "Application 31". Anything else is shown as it is. */
export const auditTarget = (t: string | null) => {
  if (!t) return "";
  const m = /^([a-z]+):(\d+)$/.exec(t);
  return m ? `${m[1]!.charAt(0).toUpperCase()}${m[1]!.slice(1)} ${m[2]}` : t;
};
export const OFFER_STATUS: Record<string, string> = { draft: "draft", pending_approval: "waiting for approval", approved: "approved", handed_off: "file written", rejected: "rejected", withdrawn: "withdrawn" };
export const INTERVIEW_STATUS: Record<string, string> = { planned: "planned", invited: "invite recorded", done: "done", cancelled: "cancelled" };
export const RECOMMENDATION: Record<string, string> = { strong_yes: "strong yes", yes: "yes", no: "no", strong_no: "strong no" };
export const ADAPTER_NAME: Record<string, string> = { seed: "Offline demo", package: "File for your signing tool", imap: "IMAP mailbox", ashby: "Ashby", workable: "Workable", greenhouse: "Greenhouse", calcom: "Cal.com", google: "Google Calendar", breezedoc: "Breezedoc" };
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
