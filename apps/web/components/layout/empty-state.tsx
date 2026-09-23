import type { IconComponent } from "@/components/icons";

import { cn } from "@/lib/utils";

/** Empty, zero-result, "nothing here yet" and error states share one shape so they read as intentional. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  tone = "default",
}: {
  icon: IconComponent;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  tone?: "default" | "ai" | "danger";
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {/* On the photo the content stands on a plate; inside a card the plate switches itself off. */}
      <div className="on-backdrop flex max-w-md flex-col items-center [--plate-x:1.5rem] [--plate-y:1.25rem]">
        <div
          className={cn(
            "glass grid size-12 place-items-center rounded-xl",
            tone === "ai" ? "bg-ai-soft text-ai" : tone === "danger" ? "bg-destructive/12 text-destructive" : "text-muted-foreground",
          )}
        >
          <Icon className="size-5" aria-hidden />
        </div>
        <h3 className="mt-4 text-base font-semibold">{title}</h3>
        {description ? <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p> : null}
        {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
      </div>
    </div>
  );
}
