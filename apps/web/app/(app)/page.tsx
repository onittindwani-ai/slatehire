"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Badge, Button, Card, CountUp, Kanban, Sheet, Skeleton, Stat, notify } from "@sendora/ui-kit";
import { AddApplicants } from "@/components/AddApplicants";
import { MoveDialog } from "@/components/MoveDialog";
import { LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import { STAGE_LABEL, type Board, type Card as Cand, type Overview, type RoleRow } from "@/lib/types";

const COLS = ["applied", "shortlisted", "interviewing", "offer", "hired", "declined"];
type Item = Omit<Cand, "id"> & { columnId: string; id: string; appId: number };

export default function PipelinePage() {
  const qc = useQueryClient();
  const router = useRouter();
  const { canWrite } = useRole();
  const [role, setRole] = useState("");
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<Item | null>(null);
  const [ask, setAsk] = useState<{ item: Item; to: string } | null>(null);
  const down = useRef<[number, number]>([0, 0]);
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<RoleRow[]>("/roles") });
  const ov = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview") });
  const board = useQuery({ queryKey: ["board", role], queryFn: () => get<Board>(`/pipeline${role ? `?role=${role}` : ""}`) });
  const move = useMutation({
    mutationFn: (v: { id: number; to: string; note: string }) => post<{ stage: string }>(`/applications/${v.id}/move`, { to: v.to, note: v.note }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: ["board", role] });
      const prev = qc.getQueryData<Board>(["board", role]);
      if (prev) {
        const next: Board = JSON.parse(JSON.stringify(prev));
        for (const st of COLS) { const col = next[st] as { cards: Cand[]; count: number } | undefined; const i = col?.cards.findIndex((c) => c.id === v.id) ?? -1; if (col && i >= 0) { const [c] = col.cards.splice(i, 1); col.count--; if (v.to !== "declined" && next[v.to]) { (next[v.to] as { cards: Cand[]; count: number }).cards.unshift({ ...c!, stage: v.to }); (next[v.to] as { count: number }).count++; } } }
        qc.setQueryData(["board", role], next);
      }
      return { prev };
    },
    onError: (e: Error, _v, ctx) => { if (ctx?.prev) qc.setQueryData(["board", role], ctx.prev); notify.error("Not moved", e.message); },
    onSuccess: (_r, v) => notify.success(`Moved to ${STAGE_LABEL[v.to]}.`),
    onSettled: () => qc.invalidateQueries(),
  });
  if (board.isError) return <div className="cf-page"><PageHead title="Pipeline" /><LoadError error={board.error} onRetry={() => board.refetch()} what="the pipeline" /></div>;
  if (roles.isError) return <div className="cf-page"><PageHead title="Pipeline" /><LoadError error={roles.error} onRetry={() => roles.refetch()} what="the roles" /></div>;
  const items: Item[] = board.data ? COLS.flatMap((st) => ((board.data![st] as { cards: Cand[] } | undefined)?.cards ?? []).map((c) => ({ ...c, columnId: st, id: String(c.id), appId: c.id }))) : [];
  const hidden = COLS.filter((st) => { const c = board.data?.[st] as { count: number; cards: Cand[] } | undefined; return c && c.count > c.cards.length; });
  const one = roles.data?.find((r) => r.key === role);
  const f = role && one ? one.funnel : ov.data?.funnel; // the numbers follow the role picked in the filter
  const onMove = (id: string, to: string) => {
    if (!canWrite) { notify.error("Not moved", "This sign in is read only, so nobody can be moved."); return; }
    const it = items.find((x) => x.id === id)!;
    if (to === "declined") setAsk({ item: it, to }); else move.mutate({ id: it.appId, to, note: "Moved on the board." });
  };
  return (
    <div className="cf-page">
      <PageHead title="Pipeline" sub="Drag a card to move someone. You make every decision; the score is only an aid. Names are hidden while a role reads blind."
        actions={<><select className="cf-select" aria-label="Filter by role" value={role} onChange={(e) => setRole(e.target.value)}><option value="">All roles</option>{(roles.data ?? []).map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}</select>
          <Button variant="primary" onClick={() => setAdding(true)} feedback={false} disabled={!canWrite} disabledReason={READ_ONLY}>Add applicants</Button></>} />
      {ov.isError ? <LoadError error={ov.error} onRetry={() => ov.refetch()} what="the numbers" /> : !f ? <div className="cf-stats">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} height={89} />)}</div> : <div className="cf-stats">
        <Stat label="Applicants" value={f ? Object.values(f).reduce((a, b) => a + b, 0) : 0} />
        <Stat label="Waiting for a decision" value={f?.applied ?? 0} note={!role && ov.data?.unscored ? `${ov.data.unscored} not scored yet` : undefined} />
        <Stat label="In interviews" value={f?.interviewing ?? 0} />
        <Stat label="Offers out for approval" value={ov.data?.pending_approvals ?? 0} note={role ? "all roles" : undefined} />
        <Stat label="Evidence quotes found in the resume" value={ov.data?.evidence.valid_percent ?? 0} format={(n) => `${n.toFixed(0)}%`} note={ov.data ? `${ov.data.evidence.quotes} checked${role ? ", all roles" : ""}` : undefined} />
      </div>}
      {!board.data || !roles.data ? <div className="cf-cols">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={320} />)}</div> : (
        <>
          <Kanban<Item> label="Hiring pipeline" columns={COLS.map((c) => ({ id: c, title: c === "declined" ? "Decline (drop here)" : STAGE_LABEL[c]! }))} items={items} onMove={onMove} onOpen={(c) => setOpen(c)} cardLabel={(c) => `candidate ${c.name}`}
            renderCard={(c) => (
              <div className="cf-cand" onPointerDown={(e) => { down.current = [e.clientX, e.clientY]; }} onClick={(e) => { if (Math.hypot(e.clientX - down.current[0], e.clientY - down.current[1]) < 5) setOpen(c); }}>
                <strong className="cf-cand__name">{c.name}</strong>
                <span className="cf-mini">{c.role_title}</span>
                <span className="cf-cand__foot">{c.total != null ? <span className="sx-num cf-cand__score"><CountUp value={c.total} format={(n) => n.toFixed(0)} /></span> : c.attention ? <Badge tone="warning">Needs a person</Badge> : <Badge>Not scored</Badge>}{c.flags ? <Badge tone="warning">{c.flags} flag{c.flags > 1 ? "s" : ""}</Badge> : null}{c.hidden ? <Badge tone="accent">Blind</Badge> : null}</span>
              </div>)} />
          {hidden.length ? <p className="cf-mini">Each column shows the 40 highest scores, and always everyone who needs a person first. The Candidates page lists everyone.</p> : null}
        </>)}
      <AddApplicants key={String(adding)} open={adding} onOpenChange={setAdding} roles={roles.data ?? []} />
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open?.name ?? ""} description={open ? `${open.role_title}. ${STAGE_LABEL[open.stage]}.` : ""}
        actions={open ? <Button variant="primary" feedback={false} onClick={() => router.push(`/candidates/${open.appId}`)}>Open workspace</Button> : null}>
        {open ? (<Card title="At a glance"><p style={{ margin: 0 }}>{open.total != null ? `Score ${open.total.toFixed(1)} out of 100 under the locked rubric.` : "Not scored yet."} {open.flags ? `${open.flags} flag(s) to read.` : "No flags."}</p>
          <div className="sx-row" style={{ marginTop: 13 }}>{open.stage === "applied" ? <Button size="sm" disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await move.mutateAsync({ id: open.appId, to: "shortlisted", note: "Shortlisted from the board." }); setOpen(null); }}>Shortlist</Button> : null}
            {open.stage !== "hired" ? <Button size="sm" variant="danger" feedback={false} disabled={!canWrite} disabledReason={READ_ONLY} onClick={() => { setAsk({ item: open, to: "declined" }); setOpen(null); }}>Decline</Button> : null}</div></Card>) : null}
      </Sheet>
      <MoveDialog open={ask !== null} onOpenChange={(o) => !o && setAsk(null)} to={ask?.to ?? "declined"} who={ask?.item.name ?? ""} onConfirm={async (note) => { if (ask) await move.mutateAsync({ id: ask.item.appId, to: ask.to, note }); }} />
    </div>
  );
}
