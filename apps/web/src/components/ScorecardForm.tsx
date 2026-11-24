"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, SegmentedControl, notify } from "@sendora/ui-kit";
import { post } from "@/lib/api";
import type { InterviewDetail } from "@/lib/types";

const RECS = [{ value: "strong_yes", label: "Strong yes" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }, { value: "strong_no", label: "Strong no" }];

/** Five targets per criterion. Nothing about the other interviewers is shown until this is sent, and it cannot be changed afterwards. */
export function ScorecardForm({ iv }: { iv: InterviewDetail }) {
  const qc = useQueryClient();
  const [r, setR] = useState<Record<string, string>>({});
  const [c, setC] = useState<Record<string, string>>({});
  const [rec, setRec] = useState("");
  const ready = iv.kit.every((k) => r[k.criterion_id]) && rec;
  const send = useMutation({
    mutationFn: () => post(`/interviews/${iv.id}/scorecards`, { ratings: Object.fromEntries(Object.entries(r).map(([k, v]) => [k, Number(v)])), comments: c, recommendation: rec }),
    onSuccess: () => { notify.success("Scorecard sent. You can now see the others' ratings. Yours cannot be changed."); qc.invalidateQueries(); },
    onError: (e: Error) => notify.error("Not sent", e.message),
  });
  return (
    <form className="cf-stack" onSubmit={(e) => e.preventDefault()} aria-label="Your scorecard">
      {iv.kit.map((k) => (
        <fieldset key={k.criterion_id} className="cf-crit-edit">
          <legend>{k.name}</legend>
          <p style={{ margin: 0 }}>{k.question}</p>
          <p className="cf-mini" style={{ margin: 0 }}>1: {k.anchors["1"]} 3: {k.anchors["3"]} 5: {k.anchors["5"]}</p>
          <SegmentedControl label={`Rating for ${k.name}`} value={r[k.criterion_id] ?? ""} onChange={(v) => setR({ ...r, [k.criterion_id]: v })} options={["1", "2", "3", "4", "5"].map((n) => ({ value: n, label: n }))} />
          <input className="cf-select" aria-label={`Note for ${k.name}`} placeholder="A short note (optional)" maxLength={600} value={c[k.criterion_id] ?? ""} onChange={(e) => setC({ ...c, [k.criterion_id]: e.target.value })} />
        </fieldset>
      ))}
      <SegmentedControl label="Your recommendation" value={rec} onChange={setRec} options={RECS} />
      <Button variant="primary" disabled={!ready} disabledReason="Rate every criterion and choose a recommendation" onClick={async () => { await send.mutateAsync(); }}>Send scorecard</Button>
    </form>
  );
}
