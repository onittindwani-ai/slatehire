"use client";
import { animate } from "motion";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Area, AreaChart as RAreaChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { cn } from "../lib/cn";

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export interface CountUpProps {
  value: number;
  format?: (n: number) => string;
  durationMs?: number;
  className?: string;
}

/** How many decimals the target has (at most 4). Steps of the count are rounded to that many, so a custom format never prints 70.948037512176 on the way to 71. */
export function countPrecision(target: number): number {
  const s = String(target);
  const dot = s.indexOf(".");
  return dot < 0 || s.includes("e") ? 0 : Math.min(4, s.length - dot - 1);
}

/** Round one step of a count to the precision of its target. */
export function roundCountStep(step: number, target: number): number {
  return Number(step.toFixed(countPrecision(target)));
}

/** Numbers count to their new value instead of jumping. Reduced motion shows the value at once. */
export function CountUp({ value, format = (n) => Math.round(n).toLocaleString("en-US"), durationMs = 700, className }: CountUpProps) {
  const [shown, setShown] = useState(prefersReducedMotion() ? value : 0);
  const from = useRef(prefersReducedMotion() ? value : 0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setShown(value);
      from.current = value;
      return;
    }
    const controls = animate(from.current, value, {
      duration: durationMs / 1000,
      ease: [0.23, 1, 0.32, 1],
      onUpdate: (v) => {
        from.current = v;
        setShown(roundCountStep(v, value));
      },
    });
    return () => controls.stop();
  }, [value, durationMs]);
  return <span className={cn("sx-num", className)}><span className="sx-sr-only">{format(value)}</span><span aria-hidden>{format(shown)}</span></span>;
}

export function Delta({ value, suffix = "%", goodWhen = "up" }: { value: number; suffix?: string; goodWhen?: "up" | "down" }) {
  const dir = value === 0 ? "flat" : value > 0 ? "up" : "down";
  const tone = dir === "flat" ? "flat" : (dir === goodWhen ? "up" : "down");
  const Icon = dir === "flat" ? Minus : dir === "up" ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="sx-delta" data-dir={tone} aria-label={`${dir === "flat" ? "No change" : dir === "up" ? "Up" : "Down"} ${Math.abs(value)}${suffix}`}>
      <Icon size={14} aria-hidden />{Math.abs(value)}{suffix}
    </span>
  );
}

export function Stat({ label, value, format, delta, goodWhen, note }: { label: string; value: number; format?: (n: number) => string; delta?: number; goodWhen?: "up" | "down"; note?: ReactNode }) {
  return (
    <div className="sx-stat">
      <span className="sx-stat__label">{label}</span>
      <span className="sx-stat__value"><CountUp value={value} format={format} /></span>
      <span className="sx-row" style={{ gap: 8 }}>
        {delta !== undefined ? <Delta value={delta} goodWhen={goodWhen} /> : null}
        {note ? <span className="sx-quiet" style={{ fontSize: 13 }}>{note}</span> : null}
      </span>
    </div>
  );
}

export interface GaugeProps {
  /** 0 to 1 */
  value: number;
  size?: number;
  label?: string;
  display?: string;
}

/** Ring gauge that draws in once on mount and eases on change. */
export function Gauge({ value, size = 144, label, display }: GaugeProps) {
  const clamped = Math.min(1, Math.max(0, value));
  const stroke = 13;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const [drawn, setDrawn] = useState(prefersReducedMotion() ? clamped : 0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setDrawn(clamped));
    return () => cancelAnimationFrame(id);
  }, [clamped]);
  return (
    <div className="sx-gauge" style={{ width: size, height: size }} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(clamped * 100)} aria-label={label ?? "Gauge"}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle className="sx-gauge__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} />
        <circle className="sx-gauge__bar" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} strokeDasharray={c} strokeDashoffset={c * (1 - drawn)} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </svg>
      <div className="sx-gauge__center">
        <span className="sx-serif sx-num" style={{ fontSize: size * 0.27 }}>{display ?? `${Math.round(clamped * 100)}%`}</span>
        {label ? <span className="sx-quiet" style={{ fontSize: 12 }}>{label}</span> : null}
      </div>
    </div>
  );
}

export function Sparkline({ data, width = 120, height = 34, label = "Trend" }: { data: number[]; width?: number; height?: number; label?: string }) {
  const { line, area } = useMemo(() => {
    if (data.length < 2) return { line: "", area: "" };
    const min = Math.min(...data);
    const max = Math.max(...data);
    const span = max - min || 1;
    const pts = data.map((v, i) => [(i / (data.length - 1)) * width, height - 3 - ((v - min) / span) * (height - 6)] as const);
    const l = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
    return { line: l, area: `${l} L${width} ${height} L0 ${height} Z` };
  }, [data, width, height]);
  return (
    <svg className="sx-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}: ${data.length} points, last ${data[data.length - 1] ?? 0}`}>
      <path className="sx-spark__fill" d={area} />
      <path d={line} />
    </svg>
  );
}

export interface Series {
  key: string;
  label: string;
  color?: string;
}

const SERIES_COLORS = ["var(--sx-accent)", "var(--sx-ink-2)", "var(--sx-sand)"];

/** Area chart: draws in once, tooltip follows the cursor with a crosshair, legend chips toggle series. */
export function AreaChart({ data, xKey, series, height = 260 }: { data: Record<string, number | string>[]; xKey: string; series: Series[]; height?: number }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const uid = useId().replace(/:/g, "");
  return (
    <div className="sx-chart">
      <div className="sx-row" role="group" aria-label="Series" style={{ marginBottom: 8 }}>
        {series.map((s, i) => (
          <button
            key={s.key}
            type="button"
            className="sx-badge"
            aria-pressed={!hidden.has(s.key)}
            style={{ cursor: "pointer", opacity: hidden.has(s.key) ? 0.5 : 1 }}
            onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(s.key)) n.delete(s.key); else n.add(s.key); return n; })}
          >
            <span style={{ width: 8, height: 8, borderRadius: 4, background: s.color ?? SERIES_COLORS[i % 3] }} />{s.label}
          </button>
        ))}
      </div>
      <div style={{ width: "100%", height }}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <RAreaChart data={data} margin={{ top: 8, right: 8, left: -13, bottom: 0 }}>
            <defs>
              {series.map((s, i) => (
                <linearGradient key={s.key} id={`${uid}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={s.color ?? SERIES_COLORS[i % 3]} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={s.color ?? SERIES_COLORS[i % 3]} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid vertical={false} stroke="var(--sx-line)" />
            <XAxis dataKey={xKey} tickLine={false} axisLine={false} tick={{ fill: "var(--sx-ink-3)" }} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: "var(--sx-ink-3)" }} />
            <RTooltip cursor={{ stroke: "var(--sx-ink-3)", strokeDasharray: "3 3" }} contentStyle={{ background: "var(--sx-glass)", border: "1px solid var(--sx-line)", borderRadius: 10 }} />
            {series.filter((s) => !hidden.has(s.key)).map((s, i) => (
              <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color ?? SERIES_COLORS[i % 3]} strokeWidth={2} fill={`url(#${uid}-${s.key})`} isAnimationActive animationDuration={700} animationEasing="ease-out" />
            ))}
          </RAreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
