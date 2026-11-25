"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Skeleton, Tooltip, formatWhen, notify } from "@sendora/ui-kit";
import { MoveDialog } from "@/components/MoveDialog";
import { LoadError, PageHead } from "@/components/Parts";
import { ResumeViewer } from "@/components/ResumeViewer";
import { ScoreTable } from "@/components/ScoreTable";
import { DraftOffer, PlanInterview } from "@/components/WorkspaceDialogs";
import { del, get, post } from "@/lib/api";
import { READ_ONLY, useMe, useRole } from "@/lib/hooks";
import { INTERVIEW_STATUS, OFFER_STATUS } from "@/lib/labels";
import { STAGE_LABEL, type Workspace } from "@/lib/types";

export default function CandidatePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe().data;
  const { canWrite } = useRole();
  const [reveal, setReveal] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [ask, setAsk] = useState<string | null>(null);
  const [plan, setPlan] = useState(false);
  const [offer, setOffer] = useState(false);
  const [wipe, setWipe] = useState(false);
  const q = useQuery({ queryKey: ["workspace", id, reveal], queryFn: () => get<Workspace>(`/applications/${id}${reveal ? "?reveal=true" : ""}`) });
  const refresh = () => qc.invalidateQueries();
  const move = useMutation({ mutationFn: (v: { to: string; note: string }) => post<{ onboarding_tasks?: number }>(`/applications/${id}/move`, v), onSuccess: (r, v) => { notify.success(`Moved to ${STAGE_LABEL[v.to]}.${r.onboarding_tasks ? ` A 30, 60 and 90 day onboarding plan was made (${r.onboarding_tasks} tasks).` : ""}`); refresh(); }, onError: (e: Error) => notify.error("Not moved", e.message) });
  const score = useMutation({ mutationFn: () => post(`/applications/${id}/score`), onSuccess: () => { notify.success("Scored under the locked rubric."); refresh(); }, onError: (e: Error) => notify.error("Not scored", e.message) });
  const plan_ = useMutation({ mutationFn: () => post<{ tasks: number }>(`/applications/${id}/onboarding`), onSuccess: (r) => { notify.success(`Onboarding plan made: ${r.tasks} tasks over 30, 60 and 90 days.`); refresh(); }, onError: (e: Error) => notify.error("Plan not made", e.message) });
  const erase = useMutation({ mutationFn: () => del(`/candidates/${id}`), onSuccess: () => { notify.success("Personal data deleted. The neutral record and the audit log stay."); refresh(); }, onError: (e: Error) => notify.error("Not deleted", e.message) });
  if (q.isError) return <div className="cf-page"><PageHead title="Candidate" /><LoadError error={q.error} onRetry={() => q.refetch()} what="this candidate" /></div>;
  const w = q.data;
  if (!w) return <div className="cf-page"><PageHead title="Candidate" /><div className="cf-two"><Skeleton height={420} /><Skeleton height={420} /></div></div>;
  const showing = !w.person.hidden;
  const closed = ["hired", "declined", "withdrawn"].includes(w.stage);
  const nextStage = w.stage === "applied" ? "shortlisted" : null;
  return (
    <div className="cf-page">
      <PageHead title={w.person.name} sub={`${w.role.title}. ${STAGE_LABEL[w.stage]}. Code ${w.person.code}.`}
        actions={<>
          <Tooltip content={w.blind.enforced ? "The locked rubric reads this role blind until the shortlist decision. The server keeps identity hidden." : showing ? "Hide identity again" : "Show identity. This is written to the audit log."}>
            <span><Button variant={showing ? "primary" : "default"} feedback={false} aria-pressed={showing} disabled={w.blind.enforced || !canWrite} disabledReason={!canWrite ? READ_ONLY : "Blind mode is on for this role until the shortlist decision"} onClick={() => setReveal(!reveal)}>{showing ? "Identity shown" : "Blind view on"}</Button></span>
          </Tooltip>
          <Link href="/candidates" className="cf-mini">All candidates</Link></>} />
      {w.deleted ? <div className="cf-banner" role="status"><strong>Deleted.</strong> <span>Personal data was removed. Only the neutral record and the audit log remain.</span></div> : null}
      {showing ? <Card title="Contact" headingLevel={3}><p style={{ margin: 0 }}>{w.person.email ?? "No email"} {w.person.phone ? `, ${w.person.phone}` : ""} {w.person.school ? `, ${w.person.school}` : ""}. Source: {w.person.source}.</p></Card> : null}
      <div className="cf-two">
        <Card title="Resume" headingLevel={2}>
          {w.attention ? <div className="cf-flag" role="note"><strong>{w.attention === "language" ? "Not scored: language." : "Resume missing."}</strong> {w.attention === "language" ? "This resume does not look like English, and the scorer reads English words only, so it was not scored. Read it yourself. It can be shortlisted without a score." : "No readable resume arrived, so nothing was scored. Ask the applicant for a text or PDF version."}</div> : null}
          {w.resume.injection.some((x) => x.level !== "possible") ? <div className="cf-flag cf-flag--claim" role="note"><strong>This resume talks to the scorer.</strong> {`It ${w.resume.injection.filter((x) => x.level !== "possible").map((x) => x.why).join("; ")}.`} Those lines are not scored and never quoted. Read them yourself.</div> : null}
          {w.resume.injection.some((x) => x.level === "possible") ? <div className="cf-flag" role="note"><strong>Possible instruction in the text, read by a person.</strong> A line has the words of an instruction but is not aimed at the reader. It is still scored. Read it yourself.</div> : null}
          {w.resume.notes.map((n, i) => <div key={i} className="cf-flag cf-flag--claim" role="note">{n.detail}{n.private ? <span className="cf-mini"> {n.private}</span> : null}</div>)}
          {showing && w.resume.has_original_file ? <p className="cf-mini"><a href={`/api/applications/${w.id}/original`}>Open the original resume file</a></p> : null}
          {w.resume.pieces.length ? <ResumeViewer pieces={w.resume.pieces} showIdentity={showing} focus={focus} criteria={w.rubric?.criteria ?? []} scores={w.score?.items ?? []} /> : <EmptyState title="No resume text" body="The resume was deleted or never had readable text." />}
        </Card>
        <div className="cf-stack">
          {w.score && w.rubric ? (
            <Card title="Score under the locked rubric" headingLevel={2}>
              <ScoreTable criteria={w.rubric.criteria} items={w.score.items} total={w.score.total} onFocus={setFocus} active={focus} />
              {w.current_version && w.rubric.version !== w.current_version ? <div className="cf-flag" role="note"><strong>Scored under version {w.rubric.version}.</strong> Version {w.current_version} is locked now, and this person has not been read under it yet. {w.stage === "applied" ? "The next run does that." : ""}<div style={{ marginTop: 8 }}><Button size="sm" disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await score.mutateAsync(); }}>Score again under version {w.current_version}</Button></div></div> : null}
              <p className="cf-mini">Rubric version {w.rubric.version}, signature {w.rubric.fingerprint} {w.rubric.signature_ok ? "checked" : "DOES NOT MATCH"}. {w.score.scorer}.</p>
              {w.score.flags.map((f, i) => <p key={i} className="cf-flag cf-flag--claim" role="note">{f.detail}</p>)}
            </Card>
          ) : <Card title="Score" headingLevel={2}><EmptyState title="Not scored yet" body={w.rubric ? "Waiting for the next run (Run now in the top bar). You can also score this person now." : "Scoring needs a locked rubric for this role. Lock one on Roles and rubrics first."} actionLabel={w.rubric && canWrite ? "Score now" : undefined} onAction={w.rubric && canWrite ? async () => { await score.mutateAsync(); } : undefined} /></Card>}
          <Card title="Decide" headingLevel={2}>
            <div className="sx-row" style={{ flexWrap: "wrap" }}>
              {nextStage ? <Button disabled={!canWrite} disabledReason={READ_ONLY} variant="primary" onClick={async () => { await move.mutateAsync({ to: "shortlisted", note: "Shortlisted from the workspace." }); }}>Shortlist</Button> : null}
              {w.stage === "shortlisted" || w.stage === "interviewing" ? <Button disabled={!canWrite} disabledReason={READ_ONLY} onClick={() => setPlan(true)} feedback={false}>Plan an interview</Button> : null}
              {w.stage === "interviewing" && !w.offer ? <Button disabled={!canWrite} disabledReason={READ_ONLY} onClick={() => setOffer(true)} feedback={false}>Draft an offer</Button> : null}
              {w.stage === "interviewing" || w.stage === "shortlisted" ? <Button disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await move.mutateAsync({ to: w.stage === "shortlisted" ? "interviewing" : "offer", note: "Moved from the workspace." }); }}>Move to {w.stage === "shortlisted" ? "interviewing" : "offer"}</Button> : null}
              {w.stage === "offer" ? <Button disabled={!canWrite} disabledReason={READ_ONLY} variant="primary" onClick={async () => { await move.mutateAsync({ to: "hired", note: "Signed offer received." }); }}>Mark hired</Button> : null}
              {!closed ? <Button disabled={!canWrite} disabledReason={READ_ONLY} variant="danger" feedback={false} onClick={() => setAsk("declined")}>Decline</Button> : null}
              {!closed ? <Button disabled={!canWrite} disabledReason={READ_ONLY} variant="ghost" feedback={false} onClick={() => setAsk("withdrawn")}>Mark withdrawn</Button> : null}
              {me?.role === "owner" && !w.deleted ? <Button variant="ghost" feedback={false} onClick={() => setWipe(true)}>Delete personal data</Button> : null}
            </div>
            {w.decision_note ? <p className="cf-mini" style={{ marginTop: 13 }}>Last decision by {w.decided_by}: {w.decision_note}</p> : null}
          </Card>
          {w.probe_areas.length && !closed ? <Card title="Worth asking about" headingLevel={2}><p className="cf-mini" style={{ marginTop: 0 }}>The resume shows little here. The questions stay the same for everyone.</p><ul className="cf-list">{w.probe_areas.map((p) => <li key={p.criterion_id}>{p.name}: {p.why}</li>)}</ul></Card> : null}
          {w.interviews.length ? <Card title="Interviews" headingLevel={2}><ul className="cf-list">{w.interviews.map((i) => <li key={i.id}><Link href="/interviews">{i.kind}, {i.minutes} min{i.starts_at ? `, ${formatWhen(new Date(i.starts_at))}` : ""}</Link> <Badge>{INTERVIEW_STATUS[i.status] ?? i.status}</Badge></li>)}</ul></Card> : null}
          {w.offer ? <Card title="Offer" headingLevel={2}><p style={{ margin: 0 }}><Link href="/offers">{w.offer.title}</Link> <Badge tone={w.offer.status === "handed_off" ? "success" : w.offer.status === "withdrawn" ? "danger" : "warning"}>{OFFER_STATUS[w.offer.status] ?? w.offer.status}</Badge></p></Card> : null}
          {w.onboarding ? <Card title="Onboarding" headingLevel={2}><p style={{ margin: 0 }}><Link href="/onboarding">{w.onboarding.tasks.filter((t) => t.done).length} of {w.onboarding.tasks.length} tasks done</Link></p></Card> : null}
          {w.stage === "hired" && !w.onboarding && !w.deleted ? <Card title="Onboarding" headingLevel={2}><p className="cf-mini" style={{ marginTop: 0 }}>There is no 30, 60 and 90 day plan for this person yet.</p><Button variant="primary" disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await plan_.mutateAsync(); }}>Make the onboarding plan</Button></Card> : null}
          <Card title="History" headingLevel={2}><ol className="cf-list">{[...w.history].reverse().map((h, i) => <li key={i}><strong>{STAGE_LABEL[h.stage] ?? h.stage}</strong> by {h.by}, {formatWhen(new Date(h.at))}{h.note ? `. ${h.note}` : ""}</li>)}</ol></Card>
        </div>
      </div>
      <MoveDialog open={ask !== null} onOpenChange={(o) => !o && setAsk(null)} to={ask ?? "declined"} who={w.person.name} onConfirm={async (note) => { await move.mutateAsync({ to: ask!, note }); }} />
      <PlanInterview open={plan} onOpenChange={setPlan} appId={w.id} me={me?.user ?? "owner@example.test"} />
      <DraftOffer open={offer} onOpenChange={setOffer} appId={w.id} title={w.role.title} />
      <ConfirmDialog open={wipe} onOpenChange={setWipe} title="Delete personal data now?" description="The resume, name, email and contact details are removed for good, and the name is taken out of any offer text and offer file. The stage history, the neutral code and the audit log stay. This cannot be undone." confirmLabel="Delete" destructive onConfirm={async () => { await erase.mutateAsync(); router.refresh(); }} />
    </div>
  );
}
