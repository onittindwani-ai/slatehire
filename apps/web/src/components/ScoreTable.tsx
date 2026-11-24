"use client";
import { Badge, CountUp } from "@sendora/ui-kit";
import type { Criterion, ScoreItem } from "@/lib/types";

const LEVEL = ["", "Seen", "Some", "Alone", "Strong", "Led and taught"];

/** One row per criterion. Hover or focus a row to mark only that criterion's evidence in the resume. */
export function ScoreTable({ criteria, items, total, onFocus, active }: { criteria: Criterion[]; items: ScoreItem[]; total: number; onFocus: (id: string | null) => void; active: string | null }) {
  return (
    <div className="cf-scores">
      <div className="cf-total" aria-label={`Total score ${total} out of 100`}>
        <span className="cf-total__n sx-num"><CountUp value={total} format={(n) => n.toFixed(1)} /></span><span className="cf-mini">out of 100, an aid for a person, never a decision</span>
      </div>
      <ul className="cf-crit" aria-label="Criteria">
        {criteria.map((c) => {
          const it = items.find((x) => x.criterion_id === c.id);
          const v = it?.value ?? 0;
          return (
            <li key={c.id}>
              <button type="button" className="cf-crit__row" data-active={active === c.id} aria-pressed={active === c.id} disabled={!it?.quotes.length}
                onMouseEnter={() => it?.quotes.length && onFocus(c.id)} onMouseLeave={() => onFocus(null)} onFocus={() => it?.quotes.length && onFocus(c.id)} onBlur={() => onFocus(null)}
                onClick={() => onFocus(active === c.id ? null : c.id)}>
                <span className="cf-crit__name">{c.name}<span className="cf-mini"> weight {c.weight}</span></span>
                <span className="cf-dots" role="img" aria-label={it?.state === "scored" ? `Level ${v} of 5` : "Not shown in the resume"}>{[1, 2, 3, 4, 5].map((n) => <i key={n} data-on={n <= v} />)}</span>
                <span className="cf-crit__lvl">{it?.state === "scored" ? LEVEL[v] : <Badge>Not shown</Badge>}</span>
              </button>
              {it?.quotes.map((q, i) => <blockquote key={i} className="cf-quote cf-quote--small">{q.text}</blockquote>)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
