import type { Metadata } from "next";
import type { ReactNode } from "react";
import { themeInitScript } from "@sendora/ui-kit";
import "@sendora/ui-kit/styles.css";
import "./globals.css";
import { Providers } from "@/components/Providers";

export const metadata: Metadata = { title: "Slatehire", description: "A hiring and onboarding pipeline where identity stays out of the first read, every score shows its evidence and a person decides every outcome." };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-accent="rose" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
