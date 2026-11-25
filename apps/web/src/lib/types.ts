export interface Me { user: string; role: "owner" | "approver" | "viewer"; demo_mode: boolean }
export interface Settings { mode: string; effective_mode: string; kill_switch: boolean; demo_mode: boolean; problems: string[]; scorer: string; rules: { retention_days: number; fairness_min_group: number; fairness_threshold: string; min_scorecards: number; blind_default: boolean }; adapters: Record<string, string> }
export interface Overview { funnel: Record<string, number>; roles: number; roles_unlocked: number; pending_approvals: number; unscored: number; evidence: { quotes: number; invalid: number; valid_percent: number }; today: string; overdue_tasks: number }
export interface Criterion { id: string; name: string; description?: string; weight: number; anchors: Record<string, string>; look_for: string[]; question?: string }
export interface RubricRow { id: number; role_id: number; version: number; criteria: Criterion[]; locked: boolean; locked_by: string | null; locked_at: string | null; fingerprint: string; blind: boolean; redaction_version: string; signature_ok: boolean | null }
export interface RoleRow { id: number; key: string; title: string; team: string; status: string; description: string; job_post: string; applicants: number; funnel: Record<string, number>; rubric: { id: number; version: number; locked: boolean; blind: boolean } | null; scoring_rubric: number | null; ats_job_id?: string }
export interface Card { id: number; code: string; name: string; hidden: boolean; role: string; role_title: string; total: number | null; flags: number; stage: string; attention?: "resume_missing" | "language" | null }
export interface Board { [stage: string]: { count: number; cards: Card[] } | { declined: number; withdrawn: number } }
export interface AppRow { id: number; code: string; name: string; hidden: boolean; role: string; role_title: string; stage: string; total: number | null; covered: number | null; flags: number; source: string; updated_at: string | null; deleted: boolean; attention?: "resume_missing" | "language" | null }
export interface IntakeLogRow { id: number; source: string; ref: string; status: string; detail: string; at: string | null }
export interface Quote { text: string; start: number }
export interface ScoreItem { criterion_id: string; state: "scored" | "not_found" | "rejected"; value: number | null; quotes: Quote[]; rationale: string; problem?: string | null }
export interface Piece { kind: "text" | "identity"; text: string; cat?: string; original?: string; criteria?: string[] }
export interface Workspace {
  id: number; stage: string; role: { key: string; title: string }; current_version: number | null;
  person: { code: string; name: string; email: string | null; phone: string | null; school: string | null; source: string; hidden: boolean };
  blind: { enforced: boolean; showing: boolean; rubric_setting: boolean };
  history: { stage: string; by: string; at: string; note: string }[]; decided_by: string | null; decision_note: string; note?: string; attention?: "resume_missing" | "language" | null; deleted: boolean;
  rubric: { id: number; version: number; fingerprint: string; signature_ok: boolean; blind: boolean; criteria: Criterion[] } | null;
  score: { id: number; total: number; covered: number; items: ScoreItem[]; flags: { kind: string; detail: string; text?: string }[]; scorer: string; at: string } | null;
  resume: { pieces: Piece[]; counts: Record<string, number>; injection: { why: string; text: string; level?: "attack" | "possible" }[]; filename: string; notes: { kind: string; detail: string; private?: string }[]; has_original_file: boolean };
  probe_areas: { criterion_id: string; name: string; why: string }[];
  interviews: { id: number; kind: string; starts_at: string | null; minutes: number; status: string; interviewers: string[]; calendar_detail: string }[];
  offer: { id: number; status: string; title: string; start_date: string; handoff_ref: string | null } | null;
  onboarding: { tasks: { id: number; phase: number; title: string; owner: string; due_on: string; done: boolean }[]; progress: Record<string, { total: number; done: number; overdue: number }> } | null;
}
export interface InterviewRow { id: number; application_id: number; name: string; code: string; role: string; kind: string; starts_at: string | null; minutes: number; status: string; interviewers: string[]; sent: string[] }
export interface KitItem { criterion_id: string; name: string; weight: number; question: string; anchors: Record<string, string>; probes: string[] }
export interface Summary { criteria: { criterion_id: string; name: string; mean: number | null; min: number | null; max: number | null; spread: number; disagree: boolean; n: number }[]; overall: number | null; recommendations: Record<string, number>; submitted: number; invited: number; complete: boolean; disagreements: string[] }
export interface InterviewDetail extends InterviewRow { kit: KitItem[]; probe_areas: { criterion_id: string; name: string; why: string }[]; calendar_detail: string; hidden: boolean; can_submit: boolean; submitted_by: string[]; my_scorecard: { ratings: Record<string, number>; comments: Record<string, string>; recommendation: string } | null; scorecards?: { interviewer: string; ratings: Record<string, number>; comments: Record<string, string>; recommendation: string }[]; summary?: Summary }
export interface OfferRow { id: number; application_id: number; name: string; code: string; title: string; start_date: string; status: string; terms: string; body: string; handoff_ref: string | null; created_by: string; approval: { id: number; status: string; requested_by: string; decided_by: string | null } | null }
export interface OnboardingRow { application_id: number; name: string; role: string; today: string; progress: Record<string, { total: number; done: number; overdue: number }>; tasks: { id: number; phase: number; title: string; owner: string; due_on: string; done: boolean; overdue: boolean }[] }
/** A group below the floor comes back with every count left out (null) and the floor it was under in `fewer_than`. */
export interface FairnessCell { entered: number | null; selected: number | null; rate: string | null; rate_pct: number | null; ratio: string | null; ratio_dec: number | null; status: string; p_value: number | null; fewer_than?: number }
export interface FairnessPayload { min_group: number; threshold: string; flagged: string[][]; notes: string[]; disclaimer: string; stages: Record<string, { reference: string | null; notes: string[]; groups: Record<string, FairnessCell> }>; meta: { people: number; labelled: number; role: string; note: string } }
export type FairnessReportRow = { id: number; created_at: string; created_by: string; payload: FairnessPayload };
export interface FairnessResp { report: FairnessReportRow | null; latest_flagged?: FairnessReportRow | null; min_group_floor?: number; labelled: number; history: { id: number; role: string; at: string; flagged: number }[] }
export interface ApprovalRow { id: number; action: string; summary: string; risk: string; status: string; requested_by: string; decided_by: string | null; note: string | null; created_at: string; payload: Record<string, unknown>; offer: { id: number; title: string; start_date: string; terms: string; body?: string; created_by?: string; status: string; application_id: number; stage: string | null } | null }
export interface AuditRow { id: number; actor: string; action: string; target: string | null; detail: Record<string, unknown>; at: string }
export interface AdapterRow { category: string; name: string; tier: string; live_verified: boolean; notes: string; selected: boolean; env_vars: string[]; configured: boolean }
export interface Integrations { categories: string[]; adapters: AdapterRow[]; demo_mode: boolean; platform_note: string }
export const STAGE_LABEL: Record<string, string> = { applied: "Applied", shortlisted: "Shortlisted", interviewing: "Interviewing", offer: "Offer", hired: "Hired", declined: "Declined", withdrawn: "Withdrawn" };
