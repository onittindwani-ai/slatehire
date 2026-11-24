"use client";
import { AlertTriangle, Inbox, WifiOff } from "lucide-react";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Button } from "./Button";
import { cn } from "../lib/cn";

export function Skeleton({ width = "100%", height = 16, radius, className, style }: { width?: number | string; height?: number | string; radius?: number; className?: string; style?: CSSProperties }) {
  return <span className={cn("sx-skeleton", className)} style={{ width, height, borderRadius: radius, ...style }} aria-hidden />;
}

/** Skeleton rows that match the final table layout, so nothing jumps when data arrives. */
export function TableSkeleton({ rows = 6, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div role="status" aria-label="Loading" style={{ display: "grid", gap: 13, padding: 21 }}>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} style={{ display: "grid", gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: 21 }}>
          {Array.from({ length: columns }, (_, c) => <Skeleton key={c} height={16} width={c === 0 ? "80%" : "60%"} />)}
        </div>
      ))}
    </div>
  );
}

/** Empty states always offer the next action. */
export function EmptyState({ title, body, actionLabel, onAction, icon }: { title: string; body: string; actionLabel?: string; onAction?: () => void | Promise<void>; icon?: ReactNode }) {
  return (
    <div className="sx-state" role="status">
      <span className="sx-state__icon">{icon ?? <Inbox size={24} aria-hidden />}</span>
      <div className="sx-state__title">{title}</div>
      <p className="sx-state__body">{body}</p>
      {actionLabel && onAction ? <Button variant="primary" onClick={onAction}>{actionLabel}</Button> : null}
    </div>
  );
}

/** Error states say what happened and how to fix it. */
export function ErrorState({ title, whatHappened, howToFix, onRetry }: { title: string; whatHappened: string; howToFix: string; onRetry?: () => void | Promise<void> }) {
  return (
    <div className="sx-state sx-state--error" role="alert">
      <span className="sx-state__icon"><AlertTriangle size={24} aria-hidden /></span>
      <div className="sx-state__title">{title}</div>
      <p className="sx-state__body">{whatHappened}</p>
      <p className="sx-state__body"><strong>How to fix it:</strong> {howToFix}</p>
      {onRetry ? <Button onClick={onRetry}>Try again</Button> : null}
    </div>
  );
}

/** Shows a banner when the browser goes offline. */
export function OfflineBanner() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    setOnline(navigator.onLine);
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  if (online) return null;
  return <div className="sx-offline" role="status"><WifiOff size={14} aria-hidden style={{ verticalAlign: -2, marginRight: 8 }} />You are offline. Changes will wait until you reconnect.</div>;
}
