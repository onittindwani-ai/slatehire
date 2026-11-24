"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, ConfirmDialog, Field, SegmentedControl, notify } from "@sendora/ui-kit";
import { Textarea } from "@/components/Parts";
import { api, get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import type { Criterion, RubricRow } from "@/lib/types";

const BLANK = (n: number): Criterion => ({ id: `c${n}`, name: "", weight: 3, anchors: { "1": "", "3": "", "5": "" }, look_for: [], question: "" });

function Weights({ rows }: { rows: Criterion[] }) {
  const sum = rows.reduce((a, c) => a + c.weight, 0) || 1;
  return <div className="cf-weights" role="img" aria-label={`Weights: ${rows.map((c) => `${c.name || "unnamed"} ${Math.round((100 * c.weight) / sum)} percent`).join(", ")}`}>{rows.map((c, i) => <span key={c.id + i} style={{ flexGrow: c.weight }} title={`${c.name || "unnamed"}: ${Math.round((100 * c.weight) / sum)}%`} data-i={i % 5} />)}</div>;
}

/** Edit an unlocked rubric, or read a locked one. Locking is a person's decision and fixes the criteria, the weights, the blind setting and the redaction version. */
export function RubricEditor({ rubric }: { rubric: RubricRow }) {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const [rows, setRows] = useState<Criterion[]>(rubric.criteria);
  const [blind, setBlind] = useState(rubric.blind);
  const [confirm, setConfirm] = useState(false);
  const dirty = JSON.stringify(rows) !== JSON.stringify(rubric.criteria) || blind !== rubric.blind;
  const locked = rubric.locked || !canWrite; // a read only sign in sees the rubric as it stands and cannot change it
  const shown = rubric.locked;
  const problems = useQuery({ queryKey: ["rubric-check", rubric.id, rubric.criteria], queryFn: () => post<{ problems: string[] }>(`/rubrics/${rubric.id}/check`), enabled: !shown && canWrite });
  const set = (i: number, patch: Partial<Criterion>) => setRows(rows.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const save = useMutation({ mutationFn: () => api<RubricRow>(`/rubrics/${rubric.id}`, { method: "PUT", json: { criteria: rows, blind } }), onSuccess: () => { notify.success("Draft saved."); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Not saved", e.message) });
  const lock = useMutation({ mutationFn: () => post<RubricRow>(`/rubrics/${rubric.id}/lock`), onSuccess: (r) => { notify.success(`Rubric locked. Signature ${r.fingerprint}. Waiting applicants will be scored on the next run.`); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Not locked", e.message) });
  const ids = new Set<string>();
  return (
    <div className="cf-stack">
      <div className="cf-toolbar">
        <Badge tone={shown ? "success" : "warning"}>{shown ? `Version ${rubric.version} locked` : `Version ${rubric.version} draft`}</Badge>
        {shown ? <span className="cf-mini">Signature {rubric.fingerprint} {rubric.signature_ok ? "checked" : "DOES NOT MATCH"}. Locked by {rubric.locked_by}.</span> : null}
        <SegmentedControl<"on" | "off"> label="Identity while reading" value={blind ? "on" : "off"} onChange={(v) => !locked && setBlind(v === "on")} options={[{ value: "on", label: "Blind until shortlist" }, { value: "off", label: "Not blind" }]} />
      </div>
      {!canWrite && !shown ? <p className="cf-mini" style={{ margin: 0 }}>This rubric is still a draft. A read only sign in cannot change it.</p> : null}
      <Weights rows={rows} />
      {rows.map((c, i) => {
        const dup = ids.has(c.id); ids.add(c.id);
        return (
          <fieldset key={i} className="cf-crit-edit" disabled={locked}>
            <legend>Criterion {i + 1}</legend>
            <div className="cf-crit-edit__top">
              <Field label="Name" value={c.name} onChange={(v) => set(i, { name: v, id: c.id.startsWith("c") && !c.name ? v.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 30) || c.id : c.id })} validate={(v) => (v.trim() ? (dup ? "Two criteria share an id. Rename one." : null) : "Give it a name")} />
              <label className="sx-label" style={{ display: "grid", gap: 8 }}>Weight<select className="cf-select" value={c.weight} onChange={(e) => set(i, { weight: Number(e.target.value) })} aria-label={`Weight of ${c.name || `criterion ${i + 1}`}`}>{[1, 2, 3, 4, 5].map((w) => <option key={w} value={w}>{w}</option>)}</select></label>
            </div>
            {(["1", "3", "5"] as const).map((k) => <Field key={k} label={`What a ${k} looks like`} value={c.anchors[k] ?? ""} onChange={(v) => set(i, { anchors: { ...c.anchors, [k]: v } })} validate={(v) => (v.trim().length >= 8 ? null : "Write a short sentence")} />)}
            <Field label="Words to look for, separated by commas" value={c.look_for.join(", ")} onChange={(v) => set(i, { look_for: v.split(",").map((x) => x.trim()).filter(Boolean) })} hint="The offline scorer reads these. A person could rewrite them at any time before locking." />
            <Textarea label="Interview question" value={c.question ?? ""} onChange={(e) => set(i, { question: e.target.value })} />
            {!locked && rows.length > 2 ? <Button size="sm" variant="ghost" feedback={false} onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove this criterion</Button> : null}
          </fieldset>
        );
      })}
      {!locked ? (
        <>
          <div className="sx-row"><Button feedback={false} onClick={() => setRows([...rows, BLANK(rows.length + 1)])} disabled={rows.length >= 10} disabledReason="Use at most 10 criteria">Add a criterion</Button>
            <Button variant="primary" disabled={!dirty} disabledReason="Nothing changed" onClick={async () => { await save.mutateAsync(); }}>Save draft</Button>
            <Button variant="danger" feedback={false} disabled={dirty || (problems.data?.problems.length ?? 0) > 0} disabledReason={dirty ? "Save the draft first" : "Fix the problems listed below"} onClick={() => setConfirm(true)}>Lock this rubric</Button></div>
          {problems.data?.problems.length ? <ul className="cf-flag cf-flag--claim" aria-label="What would stop a lock">{problems.data.problems.map((p, i) => <li key={i}>{p}</li>)}</ul> : <p className="cf-mini">Nothing stops a lock.</p>}
        </>) : null}
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Lock this rubric?" description="After this the criteria, weights, anchors and the blind setting cannot change. A change means a new version that you lock again. Everyone is scored against the locked version." confirmLabel="Lock" destructive onConfirm={async () => { await lock.mutateAsync(); }} />
    </div>
  );
}

export function useRubrics(roleId: number) {
  return useQuery({ queryKey: ["rubrics", roleId], queryFn: () => get<RubricRow[]>(`/roles/${roleId}/rubrics`) });
}
