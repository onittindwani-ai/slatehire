"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, Field, Gauge, SegmentedControl, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { api, get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import type { OnboardingRow } from "@/lib/types";

function AddTask({ person, onClose }: { person: OnboardingRow | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [phase, setPhase] = useState<"30" | "60" | "90">("30");
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("Hiring manager");
  const [due, setDue] = useState("");
  const dueDay = due || person?.today || "";
  const ok = title.trim().length >= 5 && /^\d{4}-\d{2}-\d{2}$/.test(dueDay) && !Number.isNaN(Date.parse(dueDay));
  const m = useMutation({
    mutationFn: () => post(`/applications/${person!.application_id}/onboarding/tasks`, { phase: Number(phase), title: title.trim(), owner: owner.trim() || "Hiring manager", due_on: dueDay }),
    onSuccess: () => { notify.success("Task added."); setTitle(""); setDue(""); qc.invalidateQueries(); onClose(); },
    onError: (e: Error) => notify.error("Task not added", e.message),
  });
  return (
    <Dialog open={person !== null} onOpenChange={(o) => !o && onClose()} title={person ? `Add a task for ${person.name}` : "Add a task"} description="People own the tasks. Write what has to happen, who owns it and by when."
      actions={<><Button variant="ghost" feedback={false} onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!ok} disabledReason="Describe the task in a few words and give a date like 2027-01-15" onClick={async () => { await m.mutateAsync(); }}>Add task</Button></>}>
      <div style={{ display: "grid", gap: 21 }}>
        <SegmentedControl<"30" | "60" | "90"> label="Which part of the plan" value={phase} onChange={setPhase} options={[{ value: "30", label: "First 30 days" }, { value: "60", label: "Days 31 to 60" }, { value: "90", label: "Days 61 to 90" }]} />
        <Field label="Task" value={title} onChange={setTitle} validate={(v) => (v.trim().length >= 5 ? null : "Describe the task in a few words")} />
        <Field label="Owner" value={owner} onChange={setOwner} />
        <Field label="Due on (YYYY-MM-DD)" value={dueDay} onChange={setDue} validate={(v) => (/^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)) ? null : "Write it as 2027-01-15")} />
      </div>
    </Dialog>
  );
}

export default function OnboardingPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const [adding, setAdding] = useState<OnboardingRow | null>(null);
  const [local, setLocal] = useState<Record<number, boolean>>({}); // a tick shows at once, before the server has answered
  const q = useQuery({ queryKey: ["onboarding"], queryFn: () => get<OnboardingRow[]>("/onboarding") });
  const tick = useMutation({
    mutationFn: (v: { id: number; done: boolean }) => api(`/onboarding/tasks/${v.id}`, { method: "PATCH", json: { done: v.done } }),
    onError: (e: Error) => notify.error("Not saved", e.message),
    onSettled: async (_d, _e, v) => { await qc.invalidateQueries({ queryKey: ["onboarding"] }); setLocal((l) => { const next = { ...l }; delete next[v.id]; return next; }); qc.invalidateQueries(); },
  });
  if (q.isError) return <div className="cf-page"><PageHead title="Onboarding" /><LoadError error={q.error} onRetry={() => q.refetch()} what="onboarding plans" /></div>;
  if (!q.data) return <div className="cf-page"><PageHead title="Onboarding" /><ListSkeleton /></div>;
  return (
    <div className="cf-page">
      <PageHead title="Onboarding" sub="A 30, 60 and 90 day plan starts when someone is hired. People own the tasks and tick them off." />
      {q.data.length === 0 ? <EmptyState title="Nobody to onboard yet" body="The plan is made when you mark an applicant hired, after their offer file was written." /> : q.data.map((p) => (
        <Card key={p.application_id} title={`${p.name}, ${p.role}`} headingLevel={2}>
          <div className="sx-row" style={{ marginBottom: 13 }}><Button size="sm" feedback={false} disabled={!canWrite} disabledReason={READ_ONLY} onClick={() => setAdding(p)}>Add a task</Button></div>
          <div className="cf-cols">
            {(["30", "60", "90"] as const).map((ph) => {
              const pr = p.progress[ph]!;
              return (
                <div key={ph} className="cf-stack">
                  <div className="sx-row" style={{ alignItems: "center" }}><Gauge value={pr.total ? pr.done / pr.total : 0} size={89} label={`Days 1 to ${ph}`} display={`${pr.done}/${pr.total}`} />
                    <div><strong>{ph} days</strong>{pr.overdue ? <div><Badge tone="warning">{pr.overdue} overdue</Badge></div> : null}</div></div>
                  <ul className="cf-tasks" aria-label={`Tasks for ${ph} days`}>
                    {p.tasks.filter((t) => String(t.phase) === ph).map((t) => (
                      <li key={t.id}><label className="cf-task"><input type="checkbox" checked={local[t.id] ?? t.done} disabled={!canWrite} title={canWrite ? undefined : READ_ONLY} onChange={(e) => { setLocal((l) => ({ ...l, [t.id]: e.target.checked })); tick.mutate({ id: t.id, done: e.target.checked }); }} /><span><span style={{ textDecoration: (local[t.id] ?? t.done) ? "line-through" : "none" }}>{t.title}</span><span className="cf-mini"> {t.owner}, due {t.due_on}{t.overdue ? ", overdue" : ""}</span></span></label></li>))}
                  </ul>
                </div>);
            })}
          </div>
        </Card>))}
      <AddTask key={adding?.application_id ?? 0} person={adding} onClose={() => setAdding(null)} />
    </div>
  );
}
