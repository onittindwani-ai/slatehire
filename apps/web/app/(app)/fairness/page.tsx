"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, Field, formatWhen, notify } from "@sendora/ui-kit";
import { FileDrop, Textarea } from "@/components/Parts";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import type { FairnessCell, FairnessResp, RoleRow } from "@/lib/types";

const STEP = { shortlisted: "Shortlisted from all applicants", interviewed: "Interviewed from the shortlisted", offered: "Offered from the interviewed", hired: "Hired from the offered" } as const;

function status(c: FairnessCell) {
  if (c.status === "flagged") return <Badge tone="warning">Below four fifths of the highest rate</Badge>;
  if (c.status === "reference") return <Badge tone="accent">Highest rate, the comparison</Badge>;
  if (c.status === "too_few") return <Badge>Too few to say</Badge>;
  if (c.status === "undisclosed") return <Badge>No label given</Badge>;
  if (c.status === "not_computable") return <Badge>Nobody selected</Badge>;
  return <Badge tone="success">Within four fifths</Badge>;
}

/** Voluntary group labels, one per line as "code,label" (for example A003,B). Owner only. Nobody is guessed: a person left out counts as no label. */
function Labels() {
  const qc = useQueryClient();
  const { owner } = useRole();
  const [text, setText] = useState("");
  const parse = (t: string) => Object.fromEntries(t.split(/\r?\n/).map((l) => l.split(",").map((x) => x.trim())).filter((p) => p.length >= 2 && p[0] && p[1] && !/^code$/i.test(p[0]!)).map((p) => [p[0]!, p.slice(1).join(", ")]));
  const labels = parse(text);
  const m = useMutation({ mutationFn: () => post<{ set: number; unknown: number }>("/fairness/labels", { labels }), onSuccess: (r) => { notify.success(`${r.set} labels saved${r.unknown ? `, ${r.unknown === 1 ? "1 code was" : `${r.unknown} codes were`} not found` : ""}. Run the report again to see them.`); setText(""); qc.invalidateQueries({ queryKey: ["fairness"] }); }, onError: (e: Error) => notify.error("Labels not saved", e.message) });
  return (
    <Card title="Voluntary labels" headingLevel={2}>
      <p className="cf-mini" style={{ marginTop: 0 }}>Only the owner can import them. One line per person: the candidate code, a comma, the label they chose to give (for example A003,B). Labels are never used for scoring.</p>
      <Textarea label="Labels, one per line" value={text} onChange={(e) => setText(e.target.value)} readOnly={!owner} hint={`${Object.keys(labels).length} lines read`} />
      <div className="sx-row" style={{ marginTop: 13, flexWrap: "wrap" }}>
        <Button disabled={!owner || Object.keys(labels).length === 0} disabledReason={!owner ? "Only the owner can import labels" : "Write at least one line like A003,B"} onClick={async () => { await m.mutateAsync(); }}>Save the labels</Button>
        <FileDrop accept=".csv,.txt,text/csv,text/plain" label="Or choose a CSV file" disabled={!owner} disabledReason="Only the owner can import labels" onFile={async (f) => setText(await f.text())} />
      </div>
    </Card>
  );
}

export default function FairnessPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const [role, setRole] = useState("all");
  const [min, setMin] = useState("10");
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<RoleRow[]>("/roles") });
  const q = useQuery({ queryKey: ["fairness", role], queryFn: () => get<FairnessResp>(`/fairness?role=${role}`) });
  const run = useMutation({ mutationFn: () => post("/fairness/run", { role, min_group: Number(min) }), onSuccess: () => { notify.success("Report saved."); qc.invalidateQueries({ queryKey: ["fairness"] }); }, onError: (e: Error) => notify.error("Not run", e.message) });
  if (q.isError) return <div className="cf-page"><PageHead title="Fairness" /><LoadError error={q.error} onRetry={() => q.refetch()} what="the fairness report" /></div>;
  const rep = q.data?.report?.payload;
  const minOk = /^\d+$/.test(min) && Number(min) >= 2 && Number(min) <= 200;
  return (
    <div className="cf-page">
      <PageHead title="Fairness" sub="An indicator for a person to look at. It is not a finding of discrimination and it is not legal advice. Hiring software is regulated in some places, so check the rules where you hire." />
      <Card title="Run a report" headingLevel={2}>
        <div className="cf-toolbar">
          <label className="sx-label" style={{ display: "grid", gap: 8 }}>Role<select className="cf-select" value={role} onChange={(e) => setRole(e.target.value)}><option value="all">All roles</option>{(roles.data ?? []).map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}</select></label>
          <Field label="Smallest group to compare" inputMode="numeric" value={min} onChange={setMin} validate={(v) => (/^\d+$/.test(v) && Number(v) >= 2 && Number(v) <= 200 ? null : "Use a number from 2 to 200")} hint="Groups smaller than this are shown with counts only." />
          <Button variant="primary" disabled={!canWrite || !minOk} disabledReason={!canWrite ? READ_ONLY : "Use a number from 2 to 200"} onClick={async () => { await run.mutateAsync(); }}>Run the report</Button>
        </div>
        <p className="cf-mini">Labels are voluntary and kept apart from scoring: {q.data?.labelled ?? 0} people gave one. Anyone without a label is counted as no label. Nobody is guessed.</p>
      </Card>
      <Labels />
      {!q.data ? <ListSkeleton /> : !rep ? <EmptyState title="No report yet" body="Run one above. It counts who reached each step, by group." /> : (
        <>
          <p className="cf-flag" role="note">{rep.disclaimer} Saved {formatWhen(new Date(q.data.report!.created_at))} by {q.data.report!.created_by}. {rep.flagged.length ? `${rep.flagged.length} group step(s) are below four fifths of the highest rate: a reason to look at the process, not a verdict.` : "No group is below four fifths of the highest rate at any step."}</p>
          {(Object.keys(STEP) as (keyof typeof STEP)[]).map((st) => {
            const s = rep.stages[st]!;
            return (
              <Card key={st} title={STEP[st]} headingLevel={2}>
                <div className="cf-scroll-x"><table className="cf-table" aria-label={STEP[st]}><thead><tr><th scope="col">Group</th><th scope="col">Entered</th><th scope="col">Selected</th><th scope="col">Rate</th><th scope="col">Ratio to highest</th><th scope="col">Reading</th></tr></thead>
                  <tbody>{Object.entries(s.groups).map(([g, c]) => <tr key={g}><th scope="row">{g}</th><td className="sx-num">{c.entered}</td><td className="sx-num">{c.selected}</td><td className="sx-num">{c.rate_pct}%</td><td className="sx-num">{c.ratio_dec ?? "n/a"}</td><td>{status(c)}</td></tr>)}</tbody></table></div>
                {s.notes.includes("no_comparison") ? <p className="cf-mini">Only one group is big enough, so there is nobody to compare it with.</p> : null}
                {s.notes.includes("no_group_big_enough") ? <p className="cf-mini">No group reaches the smallest size, so no ratio is shown.</p> : null}
              </Card>);
          })}
        </>)}
    </div>
  );
}
