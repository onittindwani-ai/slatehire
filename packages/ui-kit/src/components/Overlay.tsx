"use client";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";
import { cn } from "../lib/cn";

export interface OverlayProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children?: ReactNode;
  actions?: ReactNode;
}

function Frame({ kind, open, onOpenChange, title, description, children, actions }: OverlayProps & { kind: "dialog" | "sheet" }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="sx-overlay" />
        <D.Content className={cn("sx-card sx-card--glass", kind === "dialog" ? "sx-dialog" : "sx-sheet")} aria-describedby={description ? undefined : undefined}>
          <div className="sx-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <D.Title className="sx-dialog__title">{title}</D.Title>
            <D.Close asChild>
              <Button icon size="sm" variant="ghost" feedback={false} aria-label="Close"><X size={16} aria-hidden /></Button>
            </D.Close>
          </div>
          {description ? <D.Description className="sx-dialog__desc">{description}</D.Description> : null}
          {children}
          {actions ? <div className="sx-dialog__actions">{actions}</div> : null}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

export const Dialog = (p: OverlayProps) => <Frame kind="dialog" {...p} />;
export const Sheet = (p: OverlayProps) => <Frame kind="sheet" {...p} />;

/** Destructive actions always confirm, say what happens and offer a cancel. */
export function ConfirmDialog({
  open, onOpenChange, title, description, confirmLabel = "Confirm", destructive, onConfirm,
}: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; confirmLabel?: string; destructive?: boolean; onConfirm: () => void | Promise<void> }) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      actions={
        <>
          <Button variant="ghost" feedback={false} onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant={destructive ? "danger" : "primary"}
            onClick={async () => {
              await onConfirm();
              onOpenChange(false);
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
