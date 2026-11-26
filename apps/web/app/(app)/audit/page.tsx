"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, DataTable, EmptyState, Sheet, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import { auditAction, auditTarget } from "@/lib/labels";
import type { AuditRow } from "@/lib/types";

const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
/** A detail value in words: true and false become yes and no, and a list is joined. */
const plain = (v: unknown): string => (v === true ? "yes" : v === false ? "no" : Array.isArray(v) ? v.map(plain).join(", ") : v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v));

export default function AuditPage() {
  const { owner, known } = useRole();
  const q = useQuery({ queryKey: ["audit"], queryFn: () => get<AuditRow[]>("/audit?limit=500"), enabled: owner });
  const v = useQuery({ queryKey: ["audit-verify"], queryFn: () => get<{ ok: boolean; first_bad_id: number | null; entries: number }>("/audit/verify"), enabled: owner });
  const [open, setOpen] = useState<AuditRow | null>(null);
  const columns: Column<AuditRow>[] = [
    { key: "at", header: "When", width: "190px", render: (r) => when(r.at), sortValue: (r) => r.at },
    { key: "actor", header: "Who", width: "1fr", sortValue: (r) => r.actor },
    { key: "action", header: "What", width: "1.2fr", render: (r) => auditAction(r.action), sortValue: (r) => auditAction(r.action) },
    { key: "target", header: "On", width: "1fr", render: (r) => auditTarget(r.target) },
  ];
  const check = async () => {
    const r = await v.refetch();
    if (r.data) (r.data.ok ? notify.success : notify.error)(r.data.ok ? `Chain intact: ${r.data.entries} entries checked.` : `Chain broken at entry ${r.data.first_bad_id}.`);
    else notify.error("Could not check the chain", "Try again in a moment.");
  };
  if (known && !owner) return <div className="cf-page"><PageHead title="Audit log" /><EmptyState title="The audit log is for the owner" body="It shows who did what, including who has sent a scorecard. Ask the owner if you need something from it." /></div>;
  return (
    <div className="cf-page cf-act-88">
      <PageHead title="Audit log" sub="Every change, who made it and when. Each line is chained to the one before, so an edit after the fact shows. Open a line to read it in full." actions={<Button onClick={check}>Check the chain</Button>} />
      <Card>{v.data ? <Badge tone={v.data.ok ? "success" : "danger"}>{v.data.ok ? "Chain intact" : `Chain broken at entry ${v.data.first_bad_id}`}</Badge> : v.isError ? <Badge tone="danger">Could not check</Badge> : <Badge>Checking</Badge>}</Card>
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="the audit log" /> : !q.data ? <TableSkeleton rows={8} columns={4} /> : <DataTable label="Audit log" rows={q.data} rowKey={(r) => String(r.id)} columns={columns} height={520} onRowOpen={setOpen} rowActions={(r) => <Button size="sm" feedback={false} aria-label={`Open entry ${r.id}`} onClick={() => setOpen(r)}>Open</Button>} />}
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open ? auditAction(open.action) : "Entry"} description={open ? `Entry ${open.id}, ${when(open.at)}` : undefined}>
        {open ? (
          <div className="cf-stack">
            <p style={{ margin: 0 }}>{open.actor} did this{open.target ? ` on ${auditTarget(open.target)}` : ""}.</p>
            {Object.keys(open.detail).length ? <Card title="Details" headingLevel={3}><ul className="cf-list">{Object.entries(open.detail).map(([k, x]) => <li key={k}><strong>{k.replace(/_/g, " ")}:</strong> {plain(x)}</li>)}</ul></Card> : <p className="cf-mini">No further details were kept for this entry.</p>}
          </div>) : null}
      </Sheet>
    </div>
  );
}
