import * as React from "react";

import { Check, Loader2 } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Page heading for an auth step: a confident title and one line of context. */
export function AuthHeading({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <header className="mb-7 space-y-2">
      <h1 className="text-[2rem] font-black leading-[1.05] tracking-[-0.035em] sm:text-4xl">{title}</h1>
      {children ? <p className="text-[15px] leading-relaxed text-foreground-secondary">{children}</p> : null}
    </header>
  );
}

/**
 * The primary action. While the request runs it shows a spinner and stays disabled (so a double
 * click can't submit twice); after success it confirms while the app loads.
 */
export function AuthSubmit({ pending, done, disabled, children, pendingLabel, doneLabel }: { pending: boolean; done: boolean; disabled?: boolean; children: React.ReactNode; pendingLabel: string; doneLabel: string }) {
  return (
    <Button type="submit" size="lg" disabled={pending || done || disabled} aria-busy={pending || undefined} className={cn("h-11 w-full rounded-xl text-[15px] font-bold", (pending || done) && "disabled:opacity-100")}>
      {done ? (
        <>
          <Check aria-hidden /> {doneLabel}
        </>
      ) : pending ? (
        <>
          <Loader2 className="animate-spin" aria-hidden /> {pendingLabel}
        </>
      ) : (
        children
      )}
    </Button>
  );
}
