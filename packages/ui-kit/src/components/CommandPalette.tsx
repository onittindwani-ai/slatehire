"use client";
import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { Kbd } from "./Surface";

export interface PaletteItem {
  id: string;
  label: string;
  group: string;
  keywords?: string[];
  shortcut?: string[];
  onSelect: () => void;
}

export interface CommandPaletteProps {
  items: PaletteItem[];
  open?: boolean;
  onOpenChange?: (o: boolean) => void;
  placeholder?: string;
}

/** Cmd or Ctrl plus K on every screen. Works controlled or on its own. */
export function CommandPalette({ items, open: controlled, onOpenChange, placeholder = "Search or run an action" }: CommandPaletteProps) {
  const [inner, setInner] = useState(false);
  const open = controlled ?? inner;
  const setOpen = (o: boolean) => (onOpenChange ? onOpenChange(o) : setInner(o));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const groups = [...new Set(items.map((i) => i.group))];
  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Command palette" overlayClassName="sx-overlay" contentClassName="sx-card sx-card--glass sx-cmd">
      <Command.Input placeholder={placeholder} aria-label={placeholder} />
      <Command.List>
        <Command.Empty>Nothing matches. Try a shorter word.</Command.Empty>
        {groups.map((g) => (
          <Command.Group key={g} heading={g}>
            {items.filter((i) => i.group === g).map((i) => (
              <Command.Item
                key={i.id}
                value={`${i.label} ${(i.keywords ?? []).join(" ")}`}
                onSelect={() => {
                  setOpen(false);
                  i.onSelect();
                }}
              >
                {i.label}
                {i.shortcut ? <span className="sx-cmd__hint">{i.shortcut.map((k) => <Kbd key={k}>{k}</Kbd>)}</span> : null}
              </Command.Item>
            ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}
