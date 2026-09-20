"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary. Shows a calm, generic message and a retry — never a stack trace.
 * The error itself goes to the console (and the host's error reporting) only.
 */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="grid size-11 place-items-center rounded-xl bg-destructive/10 text-destructive">
        <AlertTriangle className="size-5" aria-hidden />
      </div>
      <h1 className="text-lg font-semibold">Something went wrong</h1>
      <p className="text-sm text-muted-foreground">
        This part of Notely hit a problem. Your notes are safe. Try again, and if it keeps happening let us know
        {error.digest ? ` (reference ${error.digest})` : ""}.
      </p>
      <Button onClick={reset}>Try again</Button>
    </main>
  );
}
