"use client";
import { Check, Copy, Menu, Search } from "lucide-react";
import { useState, type ComponentType, type ReactNode } from "react";
import { Button } from "./Button";
import { Kbd } from "./Surface";
import { ThemeToggle } from "./Theme";
import { cn } from "../lib/cn";

export interface NavItem {
  id: string;
  label: string;
  icon?: ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  href?: string;
  count?: number;
}

export interface AppShellProps {
  productName: string;
  nav: NavItem[];
  activeId: string;
  onNavigate?: (id: string) => void;
  breadcrumbs?: string[];
  topRight?: ReactNode;
  onOpenPalette?: () => void;
  children: ReactNode;
}

export function AppShell({ productName, nav, activeId, onNavigate, breadcrumbs, topRight, onOpenPalette, children }: AppShellProps) {
  const [open, setOpen] = useState(false);
  const crumbs = breadcrumbs ?? [nav.find((n) => n.id === activeId)?.label ?? ""];
  return (
    <div className="sx-shell">
      <aside className="sx-sidebar" data-open={open} aria-label="Primary">
        <div className="sx-brand"><span className="sx-brand__mark" aria-hidden />{productName}</div>
        <nav className="sx-nav">
          {nav.map((n) => {
            const Icon = n.icon;
            const content = (
              <>
                {Icon ? <Icon size={18} aria-hidden /> : null}
                {n.label}
                {n.count !== undefined ? <span className="sx-nav__count">{n.count}</span> : null}
              </>
            );
            const common = { className: "sx-nav__item", "aria-current": n.id === activeId ? ("page" as const) : undefined };
            return n.href ? (
              <a key={n.id} href={n.href} {...common} onClick={() => setOpen(false)}>{content}</a>
            ) : (
              <button key={n.id} type="button" {...common} onClick={() => { onNavigate?.(n.id); setOpen(false); }}>{content}</button>
            );
          })}
        </nav>
      </aside>
      <div className="sx-main">
        <header className="sx-topbar">
          <Button icon variant="ghost" feedback={false} className="sx-menu-btn" aria-label="Open menu" aria-expanded={open} onClick={() => setOpen(!open)}><Menu size={18} aria-hidden /></Button>
          <nav className="sx-crumbs" aria-label="Breadcrumb">
            {crumbs.map((c, i) => (
              <span key={`${c}-${i}`} aria-current={i === crumbs.length - 1 ? "page" : undefined}>{i > 0 ? "/ " : ""}{c}</span>
            ))}
          </nav>
          <span className="sx-topbar__spacer" />
          {onOpenPalette ? (
            <Button size="sm" feedback={false} onClick={onOpenPalette} className="sx-search-btn">
              <Search size={14} aria-hidden />Search<Kbd>⌘</Kbd><Kbd>K</Kbd>
            </Button>
          ) : null}
          {topRight}
          <ThemeToggle />
        </header>
        <main className="sx-content" id="main">{children}</main>
      </div>
    </div>
  );
}

export function SplitView({ list, detail, className }: { list: ReactNode; detail: ReactNode; className?: string }) {
  return <div className={cn("sx-split", className)}><div>{list}</div><div>{detail}</div></div>;
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="sx-filterbar" role="search">{children}</div>;
}

/** Copy to clipboard, the icon morphs to a tick. */
export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      size="sm"
      feedback={false}
      aria-label={done ? "Copied" : label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
        } catch {
          return;
        }
        setDone(true);
        setTimeout(() => setDone(false), 1600);
      }}
    >
      {done ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
      {done ? "Copied" : label}
    </Button>
  );
}

export interface WizardStep {
  id: string;
  title: string;
  description: string;
  status: "todo" | "ok" | "error";
  /** Runs the connection test. Throw to show the error state. */
  onTest?: () => Promise<void>;
}

/** One row per integration: what it is, whether it is connected, and a Test button. */
export function ConnectionWizard({ steps, onStatus }: { steps: WizardStep[]; onStatus?: (id: string, status: "ok" | "error") => void }) {
  return (
    <div className="sx-wizard" role="list">
      {steps.map((s, i) => (
        <div key={s.id} role="listitem" className="sx-wizard__step" data-status={s.status}>
          <span className="sx-wizard__dot" aria-hidden>{s.status === "ok" ? <Check size={16} /> : i + 1}</span>
          <div>
            <div className="sx-wizard__title">{s.title}</div>
            <p className="sx-wizard__desc">{s.description}</p>
          </div>
          {s.onTest ? (
            <Button
              size="sm"
              onClick={async () => {
                try {
                  await s.onTest?.();
                  onStatus?.(s.id, "ok");
                } catch (e) {
                  onStatus?.(s.id, "error");
                  throw e;
                }
              }}
            >
              Test connection
            </Button>
          ) : null}
        </div>
      ))}
    </div>
  );
}
