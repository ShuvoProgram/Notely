import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** Empty, zero-result and "nothing here yet" states share one shape so they read as intentional. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  tone = "default",
}: {
  icon: LucideIcon;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  tone?: "default" | "ai";
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      <div
        className={cn(
          "grid size-12 place-items-center rounded-2xl ring-1 ring-glass-border",
          tone === "ai" ? "bg-ai-soft text-ai" : "bg-muted/60 text-muted-foreground",
        )}
      >
        <Icon className="size-5" aria-hidden />
      </div>
      <h3 className="mt-4 text-base font-semibold">{title}</h3>
      {description ? <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}
