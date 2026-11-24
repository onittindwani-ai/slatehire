"use client";
import { forwardRef, useEffect, useRef, useState, type ButtonHTMLAttributes, type MouseEvent, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { Tooltip } from "./Tooltip";

export type ButtonVariant = "default" | "primary" | "ghost" | "danger";

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  icon?: boolean;
  /** Force the processing state from outside (for example while a form submits). */
  loading?: boolean;
  /** Shown in a tooltip when the button is disabled, so people know why. */
  disabledReason?: string;
  /** Set false for plain navigation buttons that should not show the processing and success states. */
  feedback?: boolean;
  /** Minimum time the processing state stays visible, in ms. */
  minProcessingMs?: number;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void | Promise<void>;
  children?: ReactNode;
}

type State = "idle" | "processing" | "success";
const SUCCESS_MS = 650;

/** Every action shows hover, press, focus, then a spinner and a success tick. Errors rethrow after returning to idle. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", size = "md", icon, loading, disabledReason, feedback = true, minProcessingMs = 350, onClick, disabled, className, children, type = "button", ...rest },
  ref,
) {
  const [state, setState] = useState<State>("idle");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const effective: State = loading ? "processing" : state;

  async function handle(e: MouseEvent<HTMLButtonElement>) {
    if (disabled || effective !== "idle") return;
    if (!feedback) {
      await onClick?.(e);
      return;
    }
    setState("processing");
    const started = Date.now();
    try {
      await onClick?.(e);
      const wait = Math.max(0, minProcessingMs - (Date.now() - started));
      if (wait) await new Promise((r) => setTimeout(r, wait));
      if (!mounted.current) return;
      setState("success");
      setTimeout(() => mounted.current && setState("idle"), SUCCESS_MS);
    } catch (err) {
      if (mounted.current) setState("idle");
      throw err;
    }
  }

  const button = (
    <button
      ref={ref}
      type={type}
      className={cn("sx-btn", variant !== "default" && `sx-btn--${variant}`, size === "sm" && "sx-btn--sm", icon && "sx-btn--icon", className)}
      data-state={effective}
      aria-busy={effective === "processing" || undefined}
      aria-disabled={disabled || undefined}
      disabled={disabled && !disabledReason ? true : undefined}
      onClick={(e) => {
        if (disabled) {
          e.preventDefault();
          return;
        }
        void handle(e).catch(() => undefined);
      }}
      {...rest}
    >
      <span className="sx-btn__label">{children}</span>
      {effective === "processing" && (
        <span className="sx-btn__state" role="status" aria-label="Working">
          <span className="sx-spinner" />
        </span>
      )}
      {effective === "success" && (
        <span className="sx-btn__state" role="status" aria-label="Done">
          <svg className="sx-tick" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </span>
      )}
    </button>
  );
  if (disabled && disabledReason) return <Tooltip content={disabledReason}>{button}</Tooltip>;
  return button;
});

