"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import * as React from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
          mutations: { retry: 0 },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
        <Toaster position="bottom-right" />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
