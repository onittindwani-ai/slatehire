"use client";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Badge, Button, Card, DataTable, EmptyState, FilterBar, TableSkeleton, formatWhen, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import { STAGE_LABEL, type AppRow, type IntakeLogRow, type RoleRow } from "@/lib/types";

export default function CandidatesPage() {
  const router = useRouter();
  const [role, setRole] = useState("");
  const [stage, setStage] = useState("");
  const [text, setText] = useState("");
  const { canWrite } = useRole();
  const notAdded = useQuery({ queryKey: ["intake-log"], queryFn: () => get<IntakeLogRow[]>("/intake/log?limit=50"), enabled: canWrite });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<RoleRow[]>("/roles") });
  const q = useQuery({ queryKey: ["applications"], queryFn: () => get<AppRow[]>("/applications") });
  const rows = useMemo(() => (q.data ?? []).filter((r) => (!role || r.role === role) && (!stage || r.stage === stage) && (!text || `${r.name} ${r.code}`.toLowerCase().includes(text.toLowerCase()))), [q.data, role, stage, text]);
  const columns: Column<AppRow>[] = [
    { key: "name", header: "Candidate", width: "2fr", sortValue: (r) => r.name, render: (r) => <span><button type="button" className="cf-linkbtn" tabIndex={-1} onClick={() => router.push(`/candidates/${r.id}`)}>{r.name}</button>{r.hidden ? <> <Badge tone="accent">Blind</Badge></> : null}{r.attention === "resume_missing" ? <> <Badge tone="warning">Resume missing</Badge></> : null}</span> },
    { key: "role", header: "Role", width: "1.4fr", sortValue: (r) => r.role_title, render: (r) => r.role_title },
    { key: "stage", header: "Stage", width: "120px", sortValue: (r) => r.stage, render: (r) => STAGE_LABEL[r.stage] ?? r.stage },
    { key: "total", header: "Score", width: "80px", align: "right", sortValue: (r) => r.total ?? -1, render: (r) => (r.total == null ? "None" : r.total.toFixed(1)) },
    { key: "flags", header: "Flags", width: "70px", align: "right", sortValue: (r) => r.flags, render: (r) => String(r.flags) },
    { key: "source", header: "Source", width: "1fr", sortValue: (r) => r.source },
    { key: "updated", header: "Updated", width: "150px", sortValue: (r) => r.updated_at ?? "", render: (r) => (r.updated_at ? formatWhen(new Date(r.updated_at)) : "") },
  ];
  if (q.isError) return <div className="cf-page"><PageHead title="Candidates" /><LoadError error={q.error} onRetry={() => q.refetch()} what="candidates" /></div>;
  return (
    <div className="cf-page cf-act-88">
      <PageHead title="Candidates" sub={q.data ? `${rows.length} of ${q.data.length} shown. Press j and k to move, enter to open, or use Open.` : "Everyone who applied, for every role."} />
      <FilterBar>
        <label className="sx-label">Search<input className="cf-select" type="search" aria-label="Search by name or code" placeholder="Name or code" value={text} onChange={(e) => setText(e.target.value)} /></label>
        <select className="cf-select" aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}><option value="">All roles</option>{(roles.data ?? []).map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}</select>
        <select className="cf-select" aria-label="Stage" value={stage} onChange={(e) => setStage(e.target.value)}><option value="">All stages</option>{Object.entries(STAGE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      </FilterBar>
      {!q.data ? <TableSkeleton rows={10} columns={6} /> : rows.length === 0 ? <EmptyState title="Nobody matches" body="Clear a filter, or add applicants from the Pipeline page." /> : <DataTable label="Candidates" rows={rows} rowKey={(r) => String(r.id)} columns={columns} height={560} onRowOpen={(r) => router.push(`/candidates/${r.id}`)} rowActions={(r) => <Button size="sm" feedback={false} aria-label={`Open ${r.name}`} onClick={() => router.push(`/candidates/${r.id}`)}>Open</Button>} />}
      {canWrite ? (
        <Card title={`Not added (${notAdded.data?.length ?? 0})`} headingLevel={2}>
          <p className="cf-mini" style={{ marginTop: 0 }}>Applications that arrived by email, a form or an ATS and were not added to a pipeline, each with the reason. Nobody leaves the funnel without a line here, so a person can look at it and add them by hand.</p>
          {notAdded.isError ? <p className="cf-mini" role="alert">The list could not be loaded.</p> : !notAdded.data ? null : notAdded.data.length === 0 ? <EmptyState title="Nothing was turned away" body="Every application that came in is in the list above." /> : (
            <div className="cf-stack">{notAdded.data.map((r) => (
              <div key={r.id} className="cf-field" style={{ gridTemplateColumns: "1fr auto" }}>
                <span><strong>{r.ref || "No reference"}</strong> <Badge tone={r.status === "rejected" ? "warning" : undefined}>{r.status}</Badge><br /><span className="cf-mini">{r.source}: {r.detail}</span></span>
                <span className="cf-mini">{r.at ? formatWhen(new Date(r.at)) : ""}</span>
              </div>))}</div>)}
        </Card>) : null}
    </div>
  );
}
