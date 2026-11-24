import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "../lib/cn";
import { initials } from "../lib/format";

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  /** glass only on floating layers (menus, sheets, palettes), never on page content */
  glass?: boolean;
  lift?: boolean;
  title?: ReactNode;
  /** heading element for the title; default h2 so a page h1 is followed by h2 */
  headingLevel?: 2 | 3 | 4;
}

export function Card({ glass, lift, title, headingLevel = 2, className, children, ...rest }: CardProps) {
  const Heading = `h${headingLevel}` as "h2" | "h3" | "h4";
  return (
    <div className={cn("sx-card", glass && "sx-card--glass", lift && "sx-card--lift", className)} {...rest}>
      {title ? <Heading className="sx-card__title">{title}</Heading> : null}
      {children}
    </div>
  );
}

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "accent";

export function Badge({ tone = "neutral", children, className }: { tone?: BadgeTone; children: ReactNode; className?: string }) {
  return <span className={cn("sx-badge", tone !== "neutral" && `sx-badge--${tone}`, className)}>{children}</span>;
}

export function Avatar({ name, src, size = 34 }: { name: string; src?: string; size?: number }) {
  return (
    <span className="sx-avatar" style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }} role="img" aria-label={name}>
      {src ? <img src={src} alt="" /> : initials(name)}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="sx-kbd">{children}</kbd>;
}
