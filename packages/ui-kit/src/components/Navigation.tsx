"use client";
import * as Tabs from "@radix-ui/react-tabs";
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "../lib/cn";

export interface TabItem {
  value: string;
  label: string;
  content: ReactNode;
}

export function TabsView({ items, defaultValue, value, onValueChange }: { items: TabItem[]; defaultValue?: string; value?: string; onValueChange?: (v: string) => void }) {
  return (
    <Tabs.Root defaultValue={defaultValue ?? items[0]?.value} value={value} onValueChange={onValueChange}>
      <Tabs.List className="sx-tabs__list" aria-label="Sections">
        {items.map((i) => (
          <Tabs.Trigger key={i.value} value={i.value} className="sx-tabs__trigger">{i.label}</Tabs.Trigger>
        ))}
      </Tabs.List>
      {items.map((i) => (
        <Tabs.Content key={i.value} value={i.value} className="sx-tabs__content">{i.content}</Tabs.Content>
      ))}
    </Tabs.Root>
  );
}

export interface SegmentedProps<T extends string> {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label: string;
  className?: string;
}

/** Radio group semantics with roving focus and arrow keys. */
export function SegmentedControl<T extends string>({ value, onChange, options, label, className }: SegmentedProps<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(e: KeyboardEvent, index: number) {
    const dir = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (index + dir + options.length) % options.length;
    const opt = options[next];
    if (opt) {
      onChange(opt.value);
      refs.current[next]?.focus();
    }
  }
  return (
    <div role="radiogroup" aria-label={label} className={cn("sx-segmented", className)}>
      {options.map((o, i) => (
        <button
          key={o.value}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          className="sx-segmented__item"
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export type DateRangeValue = "today" | "7d" | "30d" | "90d";
export function DateRange({ value, onChange }: { value: DateRangeValue; onChange: (v: DateRangeValue) => void }) {
  return (
    <SegmentedControl
      label="Date range"
      value={value}
      onChange={onChange}
      options={[
        { value: "today", label: "Today" },
        { value: "7d", label: "7 days" },
        { value: "30d", label: "30 days" },
        { value: "90d", label: "90 days" },
      ]}
    />
  );
}
