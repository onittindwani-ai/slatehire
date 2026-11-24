"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, DataTable, EmptyState, Sheet, TableSkeleton, formatWhen, notify, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { ScorecardForm } from "@/components/ScorecardForm";
import { get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import { INTERVIEW_STATUS, RECOMMENDATION } from "@/lib/labels";
import type { InterviewDetail, InterviewRow } from "@/lib/types";

function Detail({ id }: { id: number }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["interview", id], queryFn: () => get<InterviewDetail>(`/interviews/${id}`) });
  const invite = useMutation({ mutationFn: () => post<{ sent: boolean; reason: string }>(`/interviews/${id}/invite`, { confirm: true }), onSuccess: (r) => { (r.sent ? notify.success : notify.info)(`${r.sent ? "Invite recorded." : "Not sent."} ${r.reason}`); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Invite failed", e.message) });
  const { canWrite } = useRole();
  const iv = q.data;
  if (q.isError) return <LoadError error={q.error} onRetry={() => q.refetch()} what="this interview" />;
  if (!iv) return <TableSkeleton rows={4} columns={2} />;
  return (
    <div className="cf-stack">
      <p style={{ margin: 0 }}>{iv.name}, {iv.role}. {iv.starts_at ? formatWhen(new Date(iv.starts_at)) : "No time set"}, {iv.minutes} minutes. Interviewers: {iv.interviewers.join(", ")}.</p>
      <div className="sx-row"><Button onClick={async () => { await invite.mutateAsync(); }} disabled={!canWrite || iv.status === "invited" || iv.status === "done"} disabledReason={!canWrite ? READ_ONLY : "An invite was already recorded"}>Send the calendar invite</Button><Link href={`/candidates/${iv.application_id}`} className="cf-mini">Open the candidate</Link></div>
      {iv.calendar_detail ? <p className="cf-mini">{iv.calendar_detail}</p> : null}
      {iv.can_submit ? <Card title="Your scorecard" headingLevel={3}><ScorecardForm iv={iv} /></Card> : null}
      {iv.hidden ? <p className="cf-flag" role="note">The other interviewers' ratings and the totals appear after you send your own scorecard. {iv.submitted_by.length} of {iv.interviewers.length} sent so far.</p> : null}
      {iv.summary ? (
        <Card title="Scorecards added up" headingLevel={3}>
          <p style={{ marginTop: 0 }}>{iv.summary.submitted === 0 ? `No scorecards yet (0 of ${iv.summary.invited}). The totals appear as they come in.` : `Overall ${iv.summary.overall ?? "none"} out of 100 from ${iv.summary.submitted} of ${iv.summary.invited} scorecards. Recommendations: ${Object.entries(iv.summary.recommendations).filter(([, n]) => n).map(([k, n]) => `${n} ${RECOMMENDATION[k] ?? k}`).join(", ") || "none yet"}.`}</p>
          <table className="cf-table" aria-label="Ratings by criterion"><thead><tr><th scope="col">Criterion</th><th scope="col">Mean</th><th scope="col">Lowest</th><th scope="col">Highest</th><th scope="col">Note</th></tr></thead>
            <tbody>{iv.summary.criteria.map((c) => <tr key={c.criterion_id}><th scope="row">{c.name}</th><td className="sx-num">{c.mean ?? "none"}</td><td className="sx-num">{c.min ?? ""}</td><td className="sx-num">{c.max ?? ""}</td><td>{c.disagree ? <Badge tone="warning">Talk about this: they differ by {c.spread}</Badge> : ""}</td></tr>)}</tbody></table>
        </Card>) : null}
      <Card title="The questions (same for everyone in this role)" headingLevel={3}><ol className="cf-list">{iv.kit.map((k) => <li key={k.criterion_id}><strong>{k.name}.</strong> {k.question}</li>)}</ol></Card>
    </div>
  );
}

export default function InterviewsPage() {
  const q = useQuery({ queryKey: ["interviews"], queryFn: () => get<InterviewRow[]>("/interviews") });
  const [open, setOpen] = useState<InterviewRow | null>(null);
  const columns: Column<InterviewRow>[] = [
    { key: "name", header: "Candidate", width: "2fr", sortValue: (r) => r.name, render: (r) => <button type="button" className="cf-linkbtn" tabIndex={-1} onClick={() => setOpen(r)}>{r.name}</button> },
    { key: "role", header: "Role", width: "1.4fr", sortValue: (r) => r.role },
    { key: "when", header: "When", width: "160px", sortValue: (r) => r.starts_at ?? "", render: (r) => (r.starts_at ? formatWhen(new Date(r.starts_at)) : "Not set") },
    { key: "status", header: "Status", width: "130px", sortValue: (r) => r.status, render: (r) => <Badge tone={r.status === "done" ? "success" : "neutral"}>{INTERVIEW_STATUS[r.status] ?? r.status}</Badge> },
    { key: "sent", header: "Scorecards", width: "110px", align: "right", sortValue: (r) => r.sent.length, render: (r) => `${r.sent.length} of ${r.interviewers.length}` },
  ];
  if (q.isError) return <div className="cf-page"><PageHead title="Interviews" /><LoadError error={q.error} onRetry={() => q.refetch()} what="interviews" /></div>;
  return (
    <div className="cf-page cf-act-88">
      <PageHead title="Interviews" sub="Same questions for everyone in a role. Each interviewer rates alone first; the totals are added up by code. Open an interview to see its questions and scorecards." />
      {!q.data ? <TableSkeleton rows={8} columns={5} /> : q.data.length === 0 ? <EmptyState title="No interviews yet" body="Shortlist someone, then plan an interview from their workspace." /> : <DataTable label="Interviews" rows={q.data} rowKey={(r) => String(r.id)} columns={columns} height={460} onRowOpen={setOpen} rowActions={(r) => <Button size="sm" feedback={false} aria-label={`Open the interview with ${r.name}`} onClick={() => setOpen(r)}>Open</Button>} />}
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open ? `Interview: ${open.name}` : ""} description={open ? open.role : ""}>{open ? <Detail id={open.id} /> : null}</Sheet>
    </div>
  );
}
