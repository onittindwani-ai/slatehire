"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, notify } from "@sendora/ui-kit";
import { ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { READ_ONLY, useRole } from "@/lib/hooks";
import { ADAPTER_NAME } from "@/lib/labels";
import type { Integrations } from "@/lib/types";

const TITLE: Record<string, string> = { ats: "Applicant tracking (read only)", calendar: "Interview invites", mailbox: "Application emails (read only)", handoff: "Offer hand off to your signing tool" };
const STEPS = ["Pick what you use", "Add the settings on the server", "Test", "Stay in draft mode until the checklist is done"];

export default function IntegrationsPage() {
  const { canWrite } = useRole();
  const q = useQuery({ queryKey: ["integrations"], queryFn: () => get<Integrations>("/integrations") });
  const [results, setResults] = useState<Record<string, string>>({});
  const test = useMutation({
    mutationFn: (c: string) => post<{ ok: boolean; detail: string }>(`/integrations/${c}/test`),
    onSuccess: (r, c) => { setResults((x) => ({ ...x, [c]: `${r.ok ? "Works" : "Failed"}: ${r.detail}` })); (r.ok ? notify.success : notify.error)(`${TITLE[c]} test`, r.detail); },
    onError: (e: Error) => notify.error("Could not test", e.message),
  });
  if (q.isError) return <div className="cf-page"><PageHead title="Integrations" /><LoadError error={q.error} onRetry={() => q.refetch()} what="integrations" /></div>;
  if (!q.data) return <div className="cf-page"><PageHead title="Integrations" /><ListSkeleton /></div>;
  const d = q.data;
  return (
    <div className="cf-page">
      <PageHead title="Integrations" sub="Connect your own tools. Settings are environment variables on the server, never typed into this page, so no key is ever stored in the browser." />
      <Card title="Four steps"><ol className="cf-steps">{STEPS.map((s) => <li key={s}>{s}</li>)}</ol></Card>
      {d.categories.map((c) => (
        <Card key={c} title={TITLE[c] ?? c}>
          <div className="cf-stack">
            {d.adapters.filter((a) => a.category === c).map((a) => (
              <div key={a.name} className="cf-field" style={{ gridTemplateColumns: "1fr auto" }}>
                <span><strong>{ADAPTER_NAME[a.name] ?? a.name}</strong> {a.selected ? <Badge tone="accent">In use</Badge> : null} <Badge tone={a.tier === "A" ? "success" : "warning"}>{a.tier === "A" ? "Tested against a stand in" : "Written from docs, not tested live"}</Badge>{!a.live_verified ? <Badge>Live: UNVERIFIED</Badge> : null}<br /><span className="cf-mini" style={{ fontSize: "var(--sx-text-caption)", color: "var(--sx-ink-2)" }}>{a.notes}{a.env_vars.length ? ` Needs: ${a.env_vars.join(", ")}.` : ""}{a.selected && !a.configured ? " Some settings are missing." : ""}</span></span>
              </div>))}
            <div className="sx-row"><Button disabled={!canWrite} disabledReason={READ_ONLY} onClick={async () => { await test.mutateAsync(c); }}>Test the one in use</Button>{results[c] ? <span role="status" className="cf-mini">{results[c]}</span> : null}</div>
          </div>
        </Card>))}
    </div>
  );
}
