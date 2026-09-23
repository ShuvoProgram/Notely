import { formatLegalDate, LEGAL } from "@/lib/legal";
import { cn } from "@/lib/utils";

/** Typography for the legal documents: readable line length, generous spacing, no plugin. */
export function LegalArticle({ title, intro, children }: { title: string; intro: string; children: React.ReactNode }) {
  return (
    <article className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
      <header className="mb-10 border-b pb-8">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
        <p className="mt-3 text-sm text-muted-foreground">Last updated {formatLegalDate(LEGAL.lastUpdated)}</p>
        <p className="mt-5 text-base leading-7 text-muted-foreground">{intro}</p>
      </header>
      <div className="space-y-10">{children}</div>
    </article>
  );
}

export function LegalSection({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-24 space-y-4">
      <h2 id={`${id}-heading`} className="text-xl font-semibold tracking-tight">
        {title}
      </h2>
      <div className="space-y-4 text-[15px] leading-7 text-foreground [&_a]:underline [&_a]:underline-offset-4 [&_li]:leading-7 [&_strong]:font-semibold [&_strong]:text-foreground [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-6">
        {children}
      </div>
    </section>
  );
}

export function LegalToc({ items }: { items: { id: string; title: string }[] }) {
  return (
    <nav aria-label="On this page" className={cn("mb-10 rounded-lg border bg-card p-4 text-sm sm:p-5")}>
      <p className="mb-3 font-medium">On this page</p>
      <ol className="grid gap-1.5 sm:grid-cols-2">
        {items.map((item, i) => (
          <li key={item.id}>
            <a href={`#${item.id}`} className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
              {i + 1}. {item.title}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
