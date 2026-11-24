"use client";
import { forwardRef, useEffect, useRef, useState, type ReactNode, type TextareaHTMLAttributes } from "react";
import { ErrorState, Skeleton } from "@sendora/ui-kit";
import { ApiError } from "@/lib/api";

export function PageHead({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div className="cf-head">
      <div>
        <h1 className="cf-title">{title}</h1>
        {sub ? <p className="cf-sub">{sub}</p> : null}
      </div>
      {actions ? <div className="sx-row">{actions}</div> : null}
    </div>
  );
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string | null }>(function Textarea({ label, hint, error, id, ...rest }, ref) {
  const tid = id ?? `ta-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="sx-field">
      <label className="sx-label" htmlFor={tid}>{label}</label>
      <textarea ref={ref} id={tid} className="cf-textarea" aria-invalid={error ? true : undefined} aria-describedby={error ? `${tid}-e` : hint ? `${tid}-h` : undefined} {...rest} />
      {error ? <span id={`${tid}-e`} className="sx-field__error" role="alert">{error}</span> : hint ? <span id={`${tid}-h`} className="sx-field__hint">{hint}</span> : null}
    </div>
  );
}) ;

export function LoadError({ error, onRetry, what }: { error: unknown; onRetry: () => void; what: string }) {
  const msg = error instanceof ApiError ? error.message : "Something went wrong.";
  const missing = error instanceof ApiError && error.status === 404;
  return <ErrorState title={missing ? `Could not find ${what}` : `Could not load ${what}`} whatHappened={msg} howToFix={missing ? "It may have been removed, or the address is old. Use the sidebar to go back to a list." : "Check that the API is running and you are signed in, then try again."} onRetry={onRetry} />;
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: "grid", gap: 13, padding: 8 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} style={{ display: "grid", gap: 8 }}><Skeleton height={16} width="45%" /><Skeleton height={13} width="80%" /></div>)}
    </div>
  );
}

/** A file dropped anywhere but on a drop zone would make the browser leave the app and open the file. Stop that on every page. */
export function useBlockStrayFileDrops() {
  useEffect(() => {
    const isFile = (e: DragEvent) => !!e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files");
    const stop = (e: DragEvent) => { if (isFile(e) && !(e.target as HTMLElement | null)?.closest?.("[data-filedrop]")) e.preventDefault(); };
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => { window.removeEventListener("dragover", stop); window.removeEventListener("drop", stop); };
  }, []);
}

/** Choose a file or drop one here. The parent decides what to do with the file. */
export function FileDrop({ accept, label, hint, disabled, disabledReason, onFile }: { accept: string; label: string; hint?: string; disabled?: boolean; disabledReason?: string; onFile: (f: File) => void | Promise<void> }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const take = (f: File | undefined) => { if (f && !disabled) void onFile(f); if (input.current) input.current.value = ""; };
  return (
    <div className="cf-drop" data-filedrop data-over={over} data-disabled={disabled || undefined}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files?.[0]); }}>
      <span>{disabled ? disabledReason : label}</span>
      <input ref={input} type="file" aria-label={label} accept={accept} disabled={disabled} onChange={(e) => take(e.target.files?.[0])} />
      {hint ? <span className="cf-mini">{hint}</span> : null}
    </div>
  );
}
