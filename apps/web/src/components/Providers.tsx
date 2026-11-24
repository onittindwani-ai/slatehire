"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { OfflineBanner, ThemeProvider, Toaster } from "@sendora/ui-kit";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: false } } }));
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider accent="rose">
        {children}
        <OfflineBanner />
        <Toaster />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
