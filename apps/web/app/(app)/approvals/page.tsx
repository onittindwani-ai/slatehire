"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, Button, Card, EmptyState, formatWhen, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import type { ApprovalRow } from "@/lib/types";

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const { canWrite, user } = useRole();
  const q = useQuery({ queryKey: ["approvals"], queryFn: () => get<ApprovalRow[]>("/approvals") });
  const decide = useMutation({
    mutationFn: (v: { id: number; approve: boolean }) => post(`/approvals/${v.id}/decide`, { approve: v.approve, note: "" }),
    onSuccess: (_r, v) => { notify.success(v.approve ? "Approved." : "Rejected."); qc.invalidateQueries(); },
    onError: (e: Error) => notify.error("Could not decide", e.message),
  });
  if (q.isError) return <div className="cf-page"><PageHead title="Approvals" /><LoadError error={q.error} onRetry={() => q.refetch()} what="approvals" /></div>;
  if (!q.data) return <div className="cf-page"><PageHead title="Approvals" /><ListSkeleton /></div>;
  const pending = q.data.filter((a) => a.status === "pending");
  const past = q.data.filter((a) => a.status !== "pending");
  return (
    <div className="cf-page">
      <PageHead title="Approvals" sub="Anything that reaches outside this app waits here for a person. The person who asked cannot approve their own request." />
      <Card title={`Waiting (${pending.length})`}>{pending.length === 0 ? <EmptyState title="Nothing waiting" body="Offers show up here. A second person decides each one." /> : (
        <div className="cf-stack">{pending.map((a) => (
          <div key={a.id} className="cf-field" style={{ gridTemplateColumns: "1fr auto" }}>
            <span><strong>{a.summary}</strong> <Badge tone={a.risk === "high" ? "danger" : "warning"}>{a.risk} risk</Badge><br /><span className="cf-mini">Asked by {a.requested_by}, {formatWhen(new Date(a.created_at))}</span>
              {a.offer ? <><br /><span className="cf-mini">Planned start {a.offer.start_date}. Terms as written by the hiring manager:</span><p className="cf-approval-text">{a.offer.terms}</p><Link href={`/candidates/${a.offer.application_id}`} className="cf-mini">Open the candidate</Link> <Link href="/offers" className="cf-mini">Open the offer</Link></> : null}</span>
            <span className="sx-row"><Button size="sm" variant="primary" disabled={!canWrite || a.requested_by === user} disabledReason={!canWrite ? READ_ONLY : "You asked for this one, so a second person has to decide it"} onClick={async () => { await decide.mutateAsync({ id: a.id, approve: true }); }}>Approve</Button><Button size="sm" disabled={!canWrite || a.requested_by === user} disabledReason={!canWrite ? READ_ONLY : "You asked for this one, so a second person has to decide it"} onClick={async () => { await decide.mutateAsync({ id: a.id, approve: false }); }}>Reject</Button></span>
          </div>))}</div>)}</Card>
      <Card title="Decided">{past.length === 0 ? <EmptyState title="No history yet" body="Decisions appear here." /> : <div className="cf-stack">{past.map((a) => <div key={a.id} className="cf-field" style={{ gridTemplateColumns: "1fr auto" }}><span>{a.summary}{a.note ? <span className="cf-mini"> ({a.note})</span> : null}</span><Badge tone={a.status === "approved" ? "success" : "neutral"}>{a.status} by {a.decided_by}</Badge></div>)}</div>}</Card>
    </div>
  );
}
