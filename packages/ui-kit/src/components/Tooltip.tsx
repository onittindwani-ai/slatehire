import * as RT from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

export interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  delay?: number;
}

/** Tooltip with a short delay and a grace period so moving between neighbours feels instant. */
export function Tooltip({ content, children, side = "top", delay = 350 }: TooltipProps) {
  return (
    <RT.Provider delayDuration={delay} skipDelayDuration={300}>
      <RT.Root>
        <RT.Trigger asChild>{children}</RT.Trigger>
        <RT.Portal>
          <RT.Content className="sx-tooltip" side={side} sideOffset={6}>
            {content}
          </RT.Content>
        </RT.Portal>
      </RT.Root>
    </RT.Provider>
  );
}
