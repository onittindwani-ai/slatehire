"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ClipboardCheck, Columns3, FileCheck2, Handshake, ListChecks, LogOut, Pause, Plug, Scale, ShieldCheck, Users } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell, Badge, Button, CommandPalette, ConfirmDialog, notify, useTheme, type PaletteItem } from "@sendora/ui-kit";
import { useBlockStrayFileDrops } from "@/components/Parts";
import { api, get, post } from "@/lib/api";
import { useLiveRefresh, useMe, useRole, useSettings } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

const NAV = [
  { id: "/", label: "Pipeline", icon: Columns3 },
  { id: "/candidates", label: "Candidates", icon: Users },
  { id: "/roles", label: "Roles and rubrics", icon: FileCheck2 },
  { id: "/interviews", label: "Interviews", icon: CalendarDays },
  { id: "/offers", label: "Offers", icon: Handshake },
  { id: "/onboarding", label: "Onboarding", icon: ListChecks },
  { id: "/fairness", label: "Fairness", icon: Scale },
  { id: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { id: "/audit", label: "Audit log", icon: ShieldCheck },
  { id: "/integrations", label: "Integrations", icon: Plug },
];

/** What a Run now did, in words: nothing a person cannot see on screen. */
function ranSummary(r: { mailbox?: { added?: number; duplicate?: number; rejected?: number }; score?: { scored?: number } }): string {
  const read = (r.mailbox?.added ?? 0) + (r.mailbox?.duplicate ?? 0) + (r.mailbox?.rejected ?? 0);
  const added = r.mailbox?.added ?? 0, scored = r.score?.scored ?? 0;
  if (!read && !scored) return "Ran the jobs. Nothing new: every demo email has already arrived and everyone waiting is scored.";
  return `Ran the jobs. ${added ? `${added} new application read. ` : read ? "An email was read, nothing was added. " : ""}${scored ? `${scored} ${scored === 1 ? "person" : "people"} scored. ` : ""}Nobody was moved.`.replace(/ $/, "");
}

export function AppFrame({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const me = useMe();
  const { canWrite, owner, known } = useRole();
  const settings = useSettings();
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview") });
  const { setChoice } = useTheme();
  const [palette, setPalette] = useState(false);
  const [confirmKill, setConfirmKill] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  useLiveRefresh();
  useBlockStrayFileDrops();
  const killOn = !!settings.data?.kill_switch;
  // Pay terms are for the owner and the approver, and the audit log is for the owner: the screens a sign in cannot read are not offered (all of them show until the role is known, so nothing jumps).
  const nav = useMemo(() => NAV.filter((n) => !known || ((n.id !== "/offers" || canWrite) && (n.id !== "/audit" || owner))), [known, canWrite, owner]);
  const active = nav.find((n) => (n.id === "/" ? path === "/" : path.startsWith(n.id)))?.id ?? (path.startsWith("/candidates") ? "/candidates" : "/");
  const refresh = () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
  const demo = me.data?.demo_mode ?? false;
  const run = useMutation({ mutationFn: () => post<Parameters<typeof ranSummary>[0]>("/demo/tick"), onSuccess: (r) => { notify.success(ranSummary(r)); refresh(); }, onError: (e: Error) => notify.error("The run failed", e.message) });
  const advance = useMutation({ mutationFn: (h: number) => post("/demo/advance", { hours: h }), onSuccess: () => { notify.info("Moved the demo clock forward one day."); refresh(); }, onError: (e: Error) => notify.error("Could not move the clock", e.message) });
  const toggleKill = useMutation({ mutationFn: (on: boolean) => post("/settings", { kill_switch: on }), onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["settings"] }); }, onError: (e: Error) => notify.error("Could not change the kill switch", e.message) });
  const reset = useMutation({ mutationFn: () => post("/demo/reset"), onSuccess: () => { notify.success("Demo data reset."); refresh(); }, onError: (e: Error) => notify.error("Could not reset", e.message) });
  const signOut = () => void api("/session", { method: "DELETE" }).catch(() => null).then(() => window.location.assign("/login"));

  // The palette lists "G then 1" to "G then 9" next to the first nine pages, so they have to work: press G, then the number, outside text fields and dialogs.
  useEffect(() => {
    let armed = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.closest("[role=dialog], [role=alertdialog]"))) return;
      if (e.key.toLowerCase() === "g") { armed = Date.now(); return; }
      if (armed && Date.now() - armed < 1500 && /^[1-9]$/.test(e.key)) { armed = 0; const target = nav[Number(e.key) - 1]; if (target) router.push(target.id); return; }
      armed = 0;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, nav]);

  const items: PaletteItem[] = useMemo(() => [
    ...nav.map((n, i) => ({ id: `go-${n.id}`, label: `Go to ${n.label}`, group: "Pages", shortcut: i < 9 ? ["G", String(i + 1)] : undefined, onSelect: () => router.push(n.id) })),
    { id: "signout", label: "Sign out", group: "Account", onSelect: signOut },
    ...(owner ? [killOn ? { id: "kill", label: "Turn the kill switch off", group: "Account", onSelect: () => toggleKill.mutate(false) } : { id: "kill", label: "Pause all (kill switch)", group: "Account", onSelect: () => setConfirmKill(true) }] : []),
    { id: "dark", label: "Switch to dark theme", group: "Actions", onSelect: () => setChoice("dark") },
    { id: "light", label: "Switch to light theme", group: "Actions", onSelect: () => setChoice("light") },
    ...(demo && canWrite ? [{ id: "run", label: "Run the jobs now", group: "Demo", onSelect: () => void run.mutateAsync() }, { id: "adv", label: "Move the demo clock forward one day", group: "Demo", onSelect: () => void advance.mutateAsync(24) }] : []),
    ...(demo && owner ? [{ id: "reset", label: "Reset the demo data", group: "Demo", onSelect: () => setConfirmReset(true) }] : []),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [router, nav, setChoice, demo, run, advance, owner, canWrite, killOn, toggleKill]);
  const s = settings.data, o = overview.data;
  const demoDate = o?.today ? new Date(`${o.today}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) : "";
  return (
    <>
      {s?.kill_switch ? (
        <div className="cf-banner cf-banner--danger" role="status"><strong>Kill switch is on.</strong> <span className="cf-hide-sm cf-grow">No calendar invite is sent and no offer file is written. Reading, scoring, deciding and approving still work.</span><span className="cf-grow cf-show-sm" /> <Button size="sm" variant="ghost" disabled={!owner} disabledReason="Only the owner can turn it off" onClick={async () => { await toggleKill.mutateAsync(false); }}>Turn it off</Button></div>
      ) : s && demo ? (
        <div className="cf-banner cf-banner--info" role="status"><strong>Demo mode.</strong> <span className="cf-grow cf-hide-sm">Sample applicants. An offline rules scorer reads the resumes, not a language model. {demoDate ? `Demo date: ${demoDate}.` : ""}</span><span className="cf-grow cf-show-sm" />
          <Button size="sm" variant="primary" disabled={!canWrite} disabledReason="Viewers cannot run jobs" onClick={async () => { await run.mutateAsync(); }}>Run now</Button>
          <Button size="sm" disabled={!canWrite} disabledReason="Viewers cannot move the clock" onClick={async () => { await advance.mutateAsync(24); }}>+1 day</Button></div>
      ) : s?.effective_mode === "draft" ? (
        <div className="cf-banner" role="status"><strong>Draft mode.</strong> <span className="cf-hide-sm">No invite or file leaves the app. Exports to a file still work.</span></div>
      ) : s ? (
        <div className="cf-banner cf-banner--live" role="status"><strong>Live.</strong> <span className="cf-hide-sm">An invite needs a confirm each time. Offers need a second person.</span></div>
      ) : settings.isError ? (
        <div className="cf-banner cf-banner--danger" role="alert"><strong>Could not read the mode.</strong> <span className="cf-hide-sm cf-grow">Check that the API is running.</span><span className="cf-grow cf-show-sm" /> <Button size="sm" variant="ghost" feedback={false} onClick={() => void settings.refetch()}>Try again</Button></div>
      ) : (
        <div className="cf-banner cf-banner--info" role="status">Checking the mode...</div>
      )}
      {me.data?.role === "viewer" ? <div className="cf-banner" role="status"><strong>Read only.</strong> <span className="cf-hide-sm">You can look at everything, and change nothing. Identities stay hidden where a role reads blind.</span></div> : null}
      <AppShell
        productName="Slatehire"
        nav={nav.map((n) => ({ ...n, count: n.id === "/approvals" ? o?.pending_approvals || undefined : undefined }))}
        activeId={active}
        onNavigate={(id) => router.push(id)}
        onOpenPalette={() => setPalette(true)}
        breadcrumbs={["Slatehire", nav.find((n) => n.id === active)?.label ?? ""]}
        topRight={
          <>
            {owner ? <Button size="sm" variant="ghost" feedback={false} className="cf-iconify" aria-label={killOn ? "Turn it off (kill switch)" : "Pause all"} onClick={() => (killOn ? toggleKill.mutate(false) : setConfirmKill(true))}><Pause size={14} aria-hidden /><span className="cf-hide-sm">{killOn ? "Turn it off" : "Pause all"}</span></Button> : null}
            {me.data ? <span className="cf-hide-sm"><Badge tone="accent">{me.data.role}</Badge></span> : null}
            <Button size="sm" variant="ghost" feedback={false} className="cf-iconify" aria-label="Sign out" onClick={signOut}><LogOut size={14} aria-hidden /><span className="cf-hide-sm">Sign out</span></Button>
          </>
        }
      >
        {children}
      </AppShell>
      <CommandPalette items={items} open={palette} onOpenChange={setPalette} placeholder="Go to a page or run an action" />
      <ConfirmDialog open={confirmKill} onOpenChange={setConfirmKill} title="Pause all sending?" description="The kill switch stops calendar invites and offer files at once. Reading, scoring, deciding and approving keep working. You can turn it off again from the banner or the top bar." confirmLabel="Pause all" destructive onConfirm={() => void toggleKill.mutateAsync(true)} />
      <ConfirmDialog open={confirmReset} onOpenChange={setConfirmReset} title="Reset the demo?" description="This puts the sample seed data back and clears everything you did in the demo." confirmLabel="Reset" destructive onConfirm={() => void reset.mutateAsync()} />
    </>
  );
}
