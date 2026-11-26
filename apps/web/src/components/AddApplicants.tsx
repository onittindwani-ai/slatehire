"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Dialog, Field, SegmentedControl, notify } from "@sendora/ui-kit";
import { FileDrop, Textarea } from "@/components/Parts";
import { api, post } from "@/lib/api";
import type { RoleRow } from "@/lib/types";

type Way = "paste" | "csv" | "file" | "ats" | "mail";
const summary = (r: Record<string, unknown>) => `${r.added ?? 0} added, ${r.duplicate ?? 0} already there, ${r.rejected ?? 0} not read.`;
const problems = (r: Record<string, unknown>) => (Array.isArray(r.problems) && r.problems.length ? ` ${String(r.problems[0])}` : "");
const EMAIL = /^\S+@\S+\.\S+$/;

export function AddApplicants({ open, onOpenChange, roles }: { open: boolean; onOpenChange: (o: boolean) => void; roles: RoleRow[] }) {
  const qc = useQueryClient();
  const [way, setWay] = useState<Way>("paste");
  const [role, setRole] = useState(roles[0]?.key ?? "");
  const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [text, setText] = useState("");
  const done = (msg: string) => { notify.success(`${msg} They stay in Applied and are scored under the locked rubric. Nobody is moved for you.`); qc.invalidateQueries(); };
  const fail = (e: Error) => notify.error("That did not work", e.message);
  const key = role || roles[0]?.key || "";
  const locked = roles.find((r) => r.key === key)?.scoring_rubric != null;
  const emailOk = !email.trim() || EMAIL.test(email.trim());
  const one = (r: { status: string; reason?: string | null }, ok: string) => {
    if (r.status === "added") { done(ok); setName(""); setEmail(""); setText(""); onOpenChange(false); }
    else if (r.status === "duplicate") notify.info("That application is already here.");
    else notify.error("Not added", r.reason ?? "The resume could not be read.");
  };
  const paste = useMutation({ mutationFn: () => post<{ status: string; reason?: string | null }>("/applicants", { name: name.trim(), email: email.trim(), role: key, resume_text: text }), onSuccess: (r) => one(r, "Applicant added."), onError: fail });
  const upCsv = useMutation({ mutationFn: async (f: File) => api<Record<string, unknown>>("/applicants/csv", { method: "POST", raw: await f.arrayBuffer(), headers: { "content-type": "text/csv" } }), onSuccess: (r) => { if (!r.added && !r.duplicate) notify.error("Nobody was added", `${summary(r)}${problems(r)}`); else { done(`${summary(r)}${problems(r)}`); onOpenChange(false); } }, onError: fail });
  const upFile = useMutation({ mutationFn: async (f: File) => api<{ status: string; reason?: string | null }>(`/applicants/file?role=${encodeURIComponent(key)}`, { method: "POST", raw: await f.arrayBuffer(), headers: { "x-filename": f.name, "x-applicant-name": encodeURIComponent(name.trim()), "x-applicant-email": encodeURIComponent(email.trim()) } }), onSuccess: (r) => one(r, "Resume added."), onError: fail });
  const nothing = (r: Record<string, number>) => !(r.added || r.duplicate || r.rejected);
  const ats = useMutation({ mutationFn: () => post<Record<string, number>>(`/intake/ats?role=${encodeURIComponent(key)}`), onSuccess: (r) => { if (nothing(r)) notify.info("Nothing new came from the ATS. The offline demo list is empty; connect your own tool on the Integrations page."); else { done(summary(r)); onOpenChange(false); } }, onError: fail });
  const mail = useMutation({ mutationFn: () => post<Record<string, number>>("/intake/mailbox"), onSuccess: (r) => { if (nothing(r)) notify.info("No new application emails. In the demo all four sample emails have already arrived."); else { done(summary(r)); onOpenChange(false); } }, onError: fail });
  const pick = (
    <label className="sx-label" style={{ display: "grid", gap: 8 }}>Role
      <select className="cf-select" value={key} onChange={(e) => setRole(e.target.value)} aria-label="Role">{roles.map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}</select>
      {!locked ? <span className="cf-mini">This role has no locked rubric yet, so nobody is scored until it is locked.</span> : null}
    </label>
  );
  const who = <><Field label="Name" value={name} onChange={setName} validate={(v) => (v.trim().length >= 2 ? null : "Enter the full name")} /><Field label="Email (optional)" type="email" value={email} onChange={setEmail} validate={(v) => (!v.trim() || EMAIL.test(v.trim()) ? null : "Add an @ and a domain, like name@company.com")} /></>;
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Add applicants" description="The resume is redacted before anything reads it. Nothing is scored until the rubric of the role is locked.">
      <div style={{ display: "grid", gap: 21 }}>
        <SegmentedControl<Way> label="How to add" value={way} onChange={setWay} options={[{ value: "paste", label: "Paste" }, { value: "csv", label: "CSV" }, { value: "file", label: "Resume file" }, { value: "ats", label: "Your ATS" }, { value: "mail", label: "Email inbox" }]} />
        {way !== "mail" && way !== "csv" ? pick : null}
        {way === "paste" ? (<>{who}<Textarea label="Resume text" value={text} onChange={(e) => setText(e.target.value)} hint={`${text.length} of 60000 characters`} /><Button variant="primary" disabled={name.trim().length < 2 || text.trim().length < 40 || !emailOk} disabledReason="Add a name, a valid email or none, and at least a few lines of resume" onClick={async () => { await paste.mutateAsync(); }}>Add applicant</Button></>) : null}
        {way === "csv" ? (<><p className="cf-mini" style={{ margin: 0 }}>Columns: name, email, phone, role, resume_text, source, school. The role column holds the role key. Up to 2,000 rows.</p><FileDrop accept=".csv,text/csv" label="Choose a CSV file or drop it here" onFile={async (f) => { await upCsv.mutateAsync(f).catch(() => null); }} /></>) : null}
        {way === "file" ? (<>{who}<FileDrop accept=".txt,.md,.pdf" label="Choose a resume file or drop it here" hint="Text, markdown or PDF with text in it. Scanned images are not read." disabled={name.trim().length < 2 || !emailOk} disabledReason="Write the name above first" onFile={async (f) => { await upFile.mutateAsync(f).catch(() => null); }} /></>) : null}
        {way === "ats" ? (<><p className="cf-mini" style={{ margin: 0 }}>Reads applicants for this role from the applicant tracking tool you set up (read only: nothing is written back). Already known people are skipped. In the demo this reads a sample list.</p><Button variant="primary" onClick={async () => { await ats.mutateAsync(); }}>Read from the ATS now</Button></>) : null}
        {way === "mail" ? (<><p className="cf-mini" style={{ margin: 0 }}>Reads new application emails now (subject: Application for the role title). In the demo the next of four sample emails arrives.</p><Button variant="primary" onClick={async () => { await mail.mutateAsync(); }}>Read the inbox now</Button></>) : null}
      </div>
    </Dialog>
  );
}
