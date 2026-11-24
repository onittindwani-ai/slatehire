"use client";
import { useEffect, useMemo, useRef } from "react";
import type { Criterion, Piece, ScoreItem } from "@/lib/types";

const TAG: Record<string, string> = { name: "NAME", email: "EMAIL", phone: "PHONE", address: "ADDRESS", link: "LINK", photo: "PHOTO", dob_age: "BIRTH OR AGE", grad_year: "YEAR", pronoun: "PRONOUN", title: "TITLE", institution: "SCHOOL", personal: "PERSONAL" };

/** The resume as the scorer saw it. Identity pieces are small tags while hidden and the original words when shown. Evidence is marked; `focus` limits the marks to one criterion. */
export function ResumeViewer({ pieces, showIdentity, focus, criteria, scores }: { pieces: Piece[]; showIdentity: boolean; focus: string | null; criteria: Criterion[]; scores: ScoreItem[] }) {
  const first = useRef<HTMLElement | null>(null);
  const names = useMemo(() => Object.fromEntries(criteria.map((c) => [c.id, c.name])), [criteria]);
  const level = useMemo(() => Object.fromEntries(scores.map((s) => [s.criterion_id, s.value])), [scores]);
  useEffect(() => { if (focus && first.current) first.current.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }, [focus]);
  let placed = false;
  return (
    <div className="cf-resume" role="document" aria-label="Resume text" data-showing={showIdentity ? "identity" : "blind"}>
      {pieces.map((p, i) => {
        if (p.kind === "identity") {
          const original = showIdentity && p.original != null ? p.original : null;
          return original != null
            ? <span key={i} className="cf-id cf-id--shown">{original}</span>
            : <span key={i} className="cf-id" title="Hidden while the resume is read" aria-label={`Hidden: ${TAG[p.cat ?? ""] ?? "identity"}`}>{TAG[p.cat ?? ""] ?? "HIDDEN"}</span>;
        }
        const marks = (p.criteria ?? []).filter((c) => !focus || c === focus);
        if (!marks.length) return <span key={i}>{p.text}</span>;
        const ref = !placed ? ((placed = true), (el: HTMLElement | null) => { first.current = el; }) : undefined;
        const label = marks.map((m) => `${names[m] ?? m}${level[m] ? `, level ${level[m]}` : ""}`).join("; ");
        return <mark key={i} ref={ref} className={`cf-ev cf-ev--${Math.min(marks.length, 3)}`} title={`Evidence for: ${label}`} data-criteria={marks.join(" ")}>{p.text}</mark>;
      })}
    </div>
  );
}
