"use client";
import { useState } from "react";
import { Button, Dialog } from "@sendora/ui-kit";
import { Textarea } from "@/components/Parts";
import { STAGE_LABEL } from "@/lib/types";

/** A person moves someone: the reason is written here, in words, and kept with their name. */
export function MoveDialog({ open, onOpenChange, to, who, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; to: string; who: string; onConfirm: (note: string) => Promise<void> }) {
  const [note, setNote] = useState("");
  const need = to === "declined" || to === "withdrawn";
  const short = need && note.trim().length < 8;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setNote(""); onOpenChange(o); }} title={`Move ${who} to ${STAGE_LABEL[to] ?? to}?`}
      description={need ? "Write the reason in your own words. A person decides every outcome, and the reason is kept with your name." : "You make this decision, not the score. A note is optional."}
      actions={<><Button variant="ghost" feedback={false} onClick={() => onOpenChange(false)}>Cancel</Button><Button variant={need ? "danger" : "primary"} disabled={short} disabledReason="Write at least a short sentence" onClick={async () => { await onConfirm(note); setNote(""); onOpenChange(false); }}>Move</Button></>}>
      <Textarea label={need ? "Reason (required)" : "Note (optional)"} value={note} onChange={(e) => setNote(e.target.value)} maxLength={600} hint={`${note.length} of 600 characters`} autoFocus />
    </Dialog>
  );
}
