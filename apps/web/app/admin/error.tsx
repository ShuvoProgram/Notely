"use client";

import { useEffect } from "react";

import { AlertTriangle, RotateCcw } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";

export default function AdminError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="glass mx-auto mt-6 max-w-lg rounded-2xl" role="alert">
      <EmptyState
        icon={AlertTriangle}
        tone="danger"
        title="This admin page hit a problem"
        description={`Nothing was changed. Try again, or pick another page${error.digest ? ` (reference ${error.digest})` : ""}.`}
        action={
          <Button onClick={reset}>
            <RotateCcw aria-hidden /> Try again
          </Button>
        }
      />
    </div>
  );
}
