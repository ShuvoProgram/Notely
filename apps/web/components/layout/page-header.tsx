import { cn } from "@/lib/utils";

/**
 * Standard page heading: optional eyebrow, title, one-line description and right-aligned
 * actions. Every top-level screen uses it so headings sit at the same place and size.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="mb-1 text-xs font-medium uppercase tracking-[0.14em] text-ai">{eyebrow}</p> : null}
        <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-[1.75rem]">{title}</h1>
        {description ? <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
