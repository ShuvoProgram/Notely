import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span className="grid size-7 place-items-center rounded-md bg-ai-soft text-ai">
        <Sparkles className="size-4" aria-hidden />
      </span>
      {compact ? <span className="sr-only">Notely AI</span> : <span>Notely</span>}
    </span>
  );
}
