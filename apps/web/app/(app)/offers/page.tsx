"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, Button, Card, CopyButton, EmptyState, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import { OFFER_STATUS } from "@/lib/labels";
import type { OfferRow } from "@/lib/types";

const TONE: Record<string, "neutral" | "success" | "warning" | "danger"> = { draft: "neutral", pending_approval: "warning", approved: "success", handed_off: "success", rejected: "danger", withdrawn: "danger" };

export default function OffersPage() {
  const qc = useQueryClient();
  const { canWrite, known } = useRole();
  const q = useQuery({ queryKey: ["offers"], queryFn: () => get<OfferRow[]>("/offers"), enabled: canWrite });
  const done = (m: string) => { notify.success(m); qc.invalidateQueries(); };
  const ask = useMutation({ mutationFn: (id: number) => post(`/offers/${id}/request-approval`), onSuccess: () => done("Sent for approval. A second person has to decide it."), onError: (e: Error) => notify.error("Not sent", e.message) });
  const hand = useMutation({ mutationFn: (id: number) => post<{ detail: string }>(`/offers/${id}/hand-off`), onSuccess: (r) => { notify.success(`Offer file written. ${r.detail}`); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Not written", e.message) });
  if (known && !canWrite) return <div className="cf-page"><PageHead title="Offers" /><EmptyState title="Offers are for the owner and the approver" body="They hold pay terms and names. Ask the owner if you need to see one." /></div>;
  if (q.isError) return <div className="cf-page"><PageHead title="Offers" /><LoadError error={q.error} onRetry={() => q.refetch()} what="offers" /></div>;
  if (!q.data) return <div className="cf-page"><PageHead title="Offers" /><ListSkeleton /></div>;
  return (
    <div className="cf-page">
      <PageHead title="Offers" sub="You write the terms. A second person approves. Slatehire then writes a file for your signing tool. It never sends anything to the candidate." />
      {q.data.length === 0 ? <EmptyState title="No offers yet" body="Draft one from the workspace of someone who has been interviewed." /> : (
        <div className="cf-cols">
          {q.data.map((o) => (
            <Card key={o.id} title={`${o.title}, ${o.name}`} headingLevel={2}>
              <p className="cf-mini" style={{ marginTop: 0 }}>Candidate {o.code}. Planned start {o.start_date}. Drafted by {o.created_by}.</p>
              <p><Badge tone={TONE[o.status] ?? "neutral"}>{OFFER_STATUS[o.status] ?? o.status}</Badge> {o.approval ? <span className="cf-mini">Approval from {o.approval.requested_by}{o.approval.decided_by ? `, decided by ${o.approval.decided_by}` : ", waiting"}</span> : null}</p>
              <details><summary>The terms and the file text</summary><pre className="cf-pre">{o.body}</pre><CopyButton value={o.body} label="Copy the text" /></details>
              <div className="sx-row" style={{ marginTop: 13 }}>
                {o.status === "draft" || o.status === "rejected" ? <Button variant="primary" disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await ask.mutateAsync(o.id); }}>Ask for approval</Button> : null}
                {o.status === "pending_approval" ? <Link href="/approvals" className="cf-mini">Waiting on the Approvals page</Link> : null}
                {o.status === "approved" ? <Button variant="primary" disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await hand.mutateAsync(o.id); }}>Write the offer file</Button> : null}
                {o.status === "withdrawn" ? <span className="cf-mini">Withdrawn: the person left the process, so no file is written.</span> : null}
                {o.status === "handed_off" ? <span className="cf-mini">File: {o.handoff_ref}. Open it in your signing tool and send it from there.</span> : null}
                <Link href={`/candidates/${o.application_id}`} className="cf-mini">Open the candidate</Link>
              </div>
            </Card>))}
        </div>)}
    </div>
  );
}
