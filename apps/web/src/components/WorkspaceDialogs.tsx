"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Dialog, Field, notify } from "@sendora/ui-kit";
import { Textarea } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

/** A date a number of days after the app's own today (the demo clock in the demo), as YYYY-MM-DD. */
function daysFrom(today: string | undefined, days: number): string {
  const d = new Date(`${today ?? new Date().toISOString().slice(0, 10)}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
const useToday = () => useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview") }).data?.today;

export function PlanInterview({ open, onOpenChange, appId, me }: { open: boolean; onOpenChange: (o: boolean) => void; appId: number; me: string }) {
  const qc = useQueryClient();
  const today = useToday();
  const demo = useMe().data?.demo_mode;
  const [who, setWho] = useState(demo ? `${me}, approver@example.test` : me);
  const [picked, setWhen] = useState<string | null>(null);
  const when = picked ?? `${daysFrom(today, 7)}T10:00`;
  const [mins, setMins] = useState("45");
  const emailsOk = who.split(",").every((x) => /^\S+@\S+\.\S+$/.test(x.trim()));
  const minsOk = /^\d+$/.test(mins) && Number(mins) >= 15 && Number(mins) <= 240;
  const past = !!when && !!today && when.slice(0, 10) < today;
  const m = useMutation({
    mutationFn: () => post(`/applications/${appId}/interviews`, { interviewers: who.split(",").map((x) => x.trim()).filter(Boolean), starts_at: when ? `${when}:00Z` : null, minutes: Number(mins) }),
    onSuccess: () => { notify.success("Interview planned. The questions are the same for everyone in this role."); qc.invalidateQueries(); onOpenChange(false); },
    onError: (e: Error) => notify.error("Could not plan the interview", e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Plan an interview" description="The kit comes from the locked rubric. Interviewers send their scorecard alone and see the others after that."
      actions={<><Button variant="ghost" feedback={false} onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" disabled={!emailsOk || !minsOk || past} disabledReason={past ? "The start time is in the past" : "Check the interviewer emails and the minutes"} onClick={async () => { await m.mutateAsync(); }}>Plan it</Button></>}>
      <div style={{ display: "grid", gap: 21 }}>
        <Field label="Interviewer emails, separated by commas" value={who} onChange={setWho} validate={(v) => (v.split(",").every((x) => /^\S+@\S+\.\S+$/.test(x.trim())) ? null : "Every interviewer needs an email like name@company.com")} />
        <label className="sx-label" style={{ display: "grid", gap: 8 }}>Starts (UTC)<input className="cf-select" type="datetime-local" value={when} min={`${today ?? ""}T00:00`} onChange={(e) => setWhen(e.target.value)} />{past ? <span className="sx-field__error" role="alert">That day has already passed.</span> : null}</label>
        <Field label="Minutes" inputMode="numeric" value={mins} onChange={setMins} validate={(v) => (/^\d+$/.test(v) && Number(v) >= 15 && Number(v) <= 240 ? null : "Use 15 to 240")} />
      </div>
    </Dialog>
  );
}

export function DraftOffer({ open, onOpenChange, appId, title }: { open: boolean; onOpenChange: (o: boolean) => void; appId: number; title: string }) {
  const qc = useQueryClient();
  const today = useToday();
  const [t, setT] = useState(title);
  const [picked, setStart] = useState<string | null>(null);
  const start = picked ?? daysFrom(today, 45);
  const startOk = /^\d{4}-\d{2}-\d{2}$/.test(start) && !Number.isNaN(Date.parse(start)) && !!today && start > today;
  const [terms, setTerms] = useState("");
  const m = useMutation({
    mutationFn: () => post(`/applications/${appId}/offer`, { title: t, start_date: start, terms }),
    onSuccess: () => { notify.success("Offer drafted. Ask a second person to approve it from the Offers page."); qc.invalidateQueries(); onOpenChange(false); },
    onError: (e: Error) => notify.error("Could not draft the offer", e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Draft an offer" description="You write the terms. Slatehire never writes pay or conditions, and never sends the offer: it makes a file for your signing tool after a second person approves."
      actions={<><Button variant="ghost" feedback={false} onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" disabled={terms.trim().length < 20 || t.trim().length < 3 || !startOk} disabledReason={t.trim().length < 3 ? "Give the job a title" : !startOk ? "The start date must be a date in the future" : "Write the terms yourself, at least a short paragraph"} onClick={async () => { await m.mutateAsync(); }}>Draft offer</Button></>}>
      <div style={{ display: "grid", gap: 21 }}>
        <Field label="Job title" value={t} onChange={setT} validate={(v) => (v.trim().length >= 3 ? null : "Give the job a title")} />
        <Field label="Planned start date (YYYY-MM-DD)" value={start} onChange={setStart} validate={(v) => (/^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)) ? (today && v <= today ? "The start date must be in the future" : null) : `Write it as ${daysFrom(today, 45)}`)} />
        <Textarea label="Terms, in your words" value={terms} onChange={(e) => setTerms(e.target.value)} hint="Pay, hours, anything agreed. Have a lawyer or your HR adviser check the final file." />
      </div>
    </Dialog>
  );
}
