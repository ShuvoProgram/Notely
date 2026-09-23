"use client";

import { useEffect } from "react";

import { AlertTriangle, RotateCcw } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";

/**
 * Error boundary inside the app shell: a failing screen shows a calm message and a retry while
 * the sidebar, search and account menu stay usable. Never a stack trace; the error goes to the
 * console (and the host's error reporting) only.
 */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="glass mx-auto mt-6 max-w-lg rounded-2xl" role="alert">
      <EmptyState
        icon={AlertTriangle}
        tone="danger"
        title="This screen hit a problem"
        description={`Your notes and tasks are safe. Try again, or pick another page from the menu${error.digest ? ` (reference ${error.digest})` : ""}.`}
        action={
          <Button onClick={reset}>
            <RotateCcw aria-hidden /> Try again
          </Button>
        }
      />
    </div>
  );
}
