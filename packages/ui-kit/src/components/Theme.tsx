"use client";
import { Moon, Sun } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "./Button";

export type ThemeChoice = "light" | "dark" | "system";
const KEY = "sx-theme";

interface Ctx {
  choice: ThemeChoice;
  resolved: "light" | "dark";
  setChoice: (c: ThemeChoice) => void;
}
const ThemeCtx = createContext<Ctx | null>(null);

/** Paste into <head> before paint so the first frame already has the right theme. */
export const themeInitScript = `(function(){try{var c=localStorage.getItem("${KEY}")||"system";var d=c==="dark"||(c==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){document.documentElement.dataset.theme="light"}})()`;

function systemDark(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children, accent }: { children: ReactNode; accent?: string }) {
  const [choice, setChoiceState] = useState<ThemeChoice>("system");
  const [sys, setSys] = useState(false);
  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY) as ThemeChoice | null;
      if (saved) setChoiceState(saved);
    } catch {
      /* storage can be blocked, the system choice still works */
    }
    setSys(systemDark());
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const on = () => setSys(systemDark());
    mq?.addEventListener?.("change", on);
    return () => mq?.removeEventListener?.("change", on);
  }, []);
  const resolved: "light" | "dark" = choice === "system" ? (sys ? "dark" : "light") : choice;
  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
    if (accent) document.documentElement.dataset.accent = accent;
  }, [resolved, accent]);

  const setChoice = useCallback((c: ThemeChoice) => {
    const apply = () => {
      setChoiceState(c);
      try {
        localStorage.setItem(KEY, c);
      } catch {
        /* ignore */
      }
    };
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition && !reduce) doc.startViewTransition(apply);
    else apply();
  }, []);
  const value = useMemo(() => ({ choice, resolved, setChoice }), [choice, resolved, setChoice]);
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): Ctx {
  const c = useContext(ThemeCtx);
  if (!c) throw new Error("useTheme must be used inside ThemeProvider.");
  return c;
}

/** Like useTheme, but returns null outside a ThemeProvider (used by parts that can work without one). */
export function useThemeOptional(): Ctx | null {
  return useContext(ThemeCtx);
}

export function ThemeToggle() {
  const { resolved, setChoice } = useTheme();
  const next = resolved === "dark" ? "light" : "dark";
  return (
    <Button icon variant="ghost" feedback={false} aria-label={`Switch to ${next} theme`} onClick={() => setChoice(next)}>
      {resolved === "dark" ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
    </Button>
  );
}
