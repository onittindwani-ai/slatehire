"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, Field, Skeleton, TabsView, notify } from "@sendora/ui-kit";
import { LoadError, PageHead, Textarea } from "@/components/Parts";
import { RubricEditor, useRubrics } from "@/components/RubricEditor";
import { api, get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import type { RoleRow } from "@/lib/types";

function RolePanel({ role }: { role: RoleRow }) {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const rubrics = useRubrics(role.id);
  const [text, setText] = useState(role.job_post);
  const save = useMutation({ mutationFn: () => api(`/roles/${role.id}`, { method: "PUT", json: { job_post: text } }), onSuccess: () => { notify.success("Job post saved."); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Not saved", e.message) });
  const [job, setJob] = useState(role.ats_job_id ?? "");
  const saveJob = useMutation({ mutationFn: () => api(`/roles/${role.id}`, { method: "PUT", json: { ats_job_id: job.trim() } }), onSuccess: () => { notify.success("ATS job id saved."); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Not saved", e.message) });
  const fresh = useMutation({ mutationFn: () => post<{ job_post: string }>(`/roles/${role.id}/job-post`), onSuccess: (r) => { setText(r.job_post); notify.info("A new draft was written from the rubric. Read it and save it if you like it."); } });
  const nv = useMutation({ mutationFn: () => post(`/roles/${role.id}/rubric`, {}), onSuccess: () => { notify.success("A new draft version was started."); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Could not start a version", e.message) });
  const latest = rubrics.data?.[0];
  return (
    <div className="cf-two">
      <Card title="Rubric" headingLevel={2}>
        {!rubrics.data ? <Skeleton height={300} /> : !latest ? <EmptyState title="No rubric yet" body="Start one: a few criteria with weights and what a 1, 3 and 5 look like. Nobody is scored until you lock it." actionLabel={canWrite ? "Start a rubric" : undefined} onAction={canWrite ? async () => { await nv.mutateAsync(); } : undefined} />
          : <><RubricEditor key={latest.id + String(latest.locked)} rubric={latest} />{latest.locked ? <div style={{ marginTop: 21 }}><Button disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await nv.mutateAsync(); }}>Start a new version</Button><p className="cf-mini">Earlier versions stay as they were. Scores keep the version they were made under.</p></div> : null}</>}
      </Card>
      <div className="cf-stack">
        <Card title="Job post" headingLevel={2}>
          <Textarea label="Job post (a person edits this)" value={text} onChange={(e) => setText(e.target.value)} readOnly={!canWrite} style={{ minHeight: 260 }} />
          <div className="sx-row" style={{ marginTop: 13 }}><Button variant="primary" disabled={!canWrite || text === role.job_post} disabledReason={!canWrite ? READ_ONLY : "Nothing changed"} onClick={async () => { await save.mutateAsync(); }}>Save</Button><Button disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await fresh.mutateAsync(); }}>Write a fresh draft</Button></div>
          <p className="cf-mini">The draft is a template filled from the rubric, not a language model. It says that applicants are read against the same written criteria.</p>
        </Card>
        <Card title="Your ATS" headingLevel={2}>
          <p className="cf-mini" style={{ marginTop: 0 }}>Only needed when you pull applicants from Ashby, Workable or Greenhouse. A pull brings in just the people who applied to this one job, so write the job id from your ATS here. Without it a pull is refused.</p>
          <div className="sx-row"><label className="sx-label">ATS job id<input className="cf-select" aria-label="ATS job id" value={job} readOnly={!canWrite} onChange={(e) => setJob(e.target.value)} /></label>
            <Button disabled={!canWrite || job.trim() === (role.ats_job_id ?? "")} disabledReason={!canWrite ? READ_ONLY : "Nothing changed"} onClick={async () => { await saveJob.mutateAsync(); }}>Save</Button></div>
        </Card>
        <Card title="Versions" headingLevel={2}><ul className="cf-list">{(rubrics.data ?? []).map((r) => <li key={r.id}>Version {r.version}: {r.locked ? <Badge tone="success">locked {r.fingerprint}</Badge> : <Badge tone="warning">draft</Badge>} {r.blind ? "blind" : "not blind"}</li>)}</ul></Card>
      </div>
    </div>
  );
}

export default function RolesPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["roles"], queryFn: () => get<RoleRow[]>("/roles") });
  const { canWrite } = useRole();
  const [tab, setTab] = useState<string | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const add = useMutation({ mutationFn: () => post<{ key: string }>("/roles", { title: title.trim(), description: desc }), onSuccess: (r) => { notify.success("Role created. Start its rubric below."); setTab(r.key); setOpen(false); setTitle(""); setDesc(""); qc.invalidateQueries(); }, onError: (e: Error) => notify.error("Could not create the role", e.message) });
  if (q.isError) return <div className="cf-page"><PageHead title="Roles and rubrics" /><LoadError error={q.error} onRetry={() => q.refetch()} what="roles" /></div>;
  return (
    <div className="cf-page">
      <PageHead title="Roles and rubrics" sub="Write what you will look for, then lock it. Everyone for the role is read against the same locked rubric." actions={<Button variant="primary" feedback={false} disabled={!canWrite} disabledReason={READ_ONLY} onClick={() => setOpen(true)}>New role</Button>} />
      {!q.data ? <Skeleton height={360} /> : q.data.length === 0 ? <EmptyState title="No roles yet" body="Create a role, write its rubric and lock it." actionLabel={canWrite ? "New role" : undefined} onAction={canWrite ? () => setOpen(true) : undefined} />
        : <TabsView value={tab ?? q.data[0]?.key} onValueChange={setTab} items={q.data.map((r) => ({ value: r.key, label: r.title, content: <RolePanel key={r.id} role={r} /> }))} />}
      <Dialog open={open} onOpenChange={setOpen} title="New role" description="A starter job post is written for you to edit."
        actions={<><Button variant="ghost" feedback={false} onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" disabled={title.trim().length < 3} disabledReason="Give the role a title" onClick={async () => { await add.mutateAsync(); }}>Create</Button></>}>
        <div style={{ display: "grid", gap: 21 }}><Field label="Title" value={title} onChange={setTitle} validate={(v) => (v.trim().length >= 3 ? null : "Give the role a title of at least 3 letters")} /><Textarea label="What the work is" value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
      </Dialog>
    </div>
  );
}
