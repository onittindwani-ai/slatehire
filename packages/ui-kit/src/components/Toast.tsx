"use client";
import { Toaster as Sonner, toast } from "sonner";
import { useThemeOptional } from "./Theme";

/** Mount once near the root. */
export function Toaster({ theme }: { theme?: "light" | "dark" | "system" }) {
  const ctx = useThemeOptional();
  return <Sonner theme={theme ?? ctx?.resolved ?? "system"} position="bottom-right" closeButton duration={5000} />;
}

export const notify = {
  success: (message: string) => toast.success(message),
  error: (message: string, fix?: string) => toast.error(message, { description: fix }),
  info: (message: string) => toast(message),
  /** Optimistic actions get a short window to undo. */
  undo: (message: string, onUndo: () => void) =>
    toast(message, { duration: 6000, action: { label: "Undo", onClick: onUndo } }),
};
