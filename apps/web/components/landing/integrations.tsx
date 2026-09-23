import { Braces, Lock } from "@/components/icons";
import { INTEGRATION_GROUPS, logoUrl } from "@/components/landing/content";
import { SectionLabel, Words } from "@/components/landing/reveal";

/** The apps Notely connects to today, grouped the way people think about them. */
export function Integrations() {
  return (
    <section id="integrations" aria-labelledby="integrations-heading" className="scroll-mt-20 border-t border-foreground/10">
      <div className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 lg:py-28">
        <SectionLabel index="03">Integrations</SectionLabel>
        <div className="mt-5 grid gap-6 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <h2 id="integrations-heading" data-reveal="words" className="text-[clamp(2.25rem,5.5vw,4rem)] font-black leading-[0.98] tracking-[-0.04em]">
            <Words text="Works with the apps you already live in." />
          </h2>
          <p data-reveal className="max-w-md text-base leading-relaxed text-foreground-secondary sm:text-lg">
            Ask across them, draft into them and schedule onto them, always with your approval.
          </p>
        </div>

        <div className="mt-14 space-y-10">
          {INTEGRATION_GROUPS.map((g) => (
            <div key={g.label} data-reveal className="grid gap-4 lg:grid-cols-[14rem_1fr] lg:gap-8">
              <h3 className="font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground lg:pt-5">{g.label}</h3>
              <ul className="grid grid-cols-2 border-l border-t border-foreground/15 sm:grid-cols-3 lg:grid-cols-6">
                {g.items.map((it) => (
                  <li key={it.name} className="landing-logo group flex items-center gap-3 border-b border-r border-foreground/15 bg-background px-4 py-4">
                    <span className="grid size-10 shrink-0 place-items-center rounded-full bg-white ring-1 ring-black/10 transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:-translate-y-0.5 group-hover:-rotate-3">
                      {it.slug ? (
                        // eslint-disable-next-line @next/next/no-img-element -- vendor SVGs from the same logo CDN the in-app marketplace uses
                        <img src={logoUrl(it.slug)} alt="" width={20} height={20} loading="lazy" decoding="async" className="size-5 grayscale transition-[filter] duration-300 group-hover:grayscale-0" />
                      ) : (
                        <span aria-hidden className="grid size-7 place-items-center rounded-full text-xs font-black text-white grayscale transition-[filter] duration-300 group-hover:grayscale-0" style={{ backgroundColor: it.mono }}>
                          {it.name.replace("Microsoft ", "").slice(0, 1)}
                        </span>
                      )}
                    </span>
                    <span className="text-sm font-medium leading-tight">{it.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div data-reveal className="mt-12 grid gap-px border border-foreground/15 bg-foreground/15 sm:grid-cols-2">
          <p className="flex items-start gap-3 bg-background p-5 text-[15px] leading-relaxed">
            <Lock className="mt-0.5 size-5 shrink-0 text-ai" aria-hidden />
            <span>
              <strong className="font-bold">Each app’s own sign-in.</strong> You connect through the vendor’s consent screen. Notely never asks for your password.
            </span>
          </p>
          <p className="flex items-start gap-3 bg-background p-5 text-[15px] leading-relaxed">
            <Braces className="mt-0.5 size-5 shrink-0 text-ai" aria-hidden />
            <span>
              <strong className="font-bold">Anything else?</strong> Plug in any MCP server and its tools work with the same approvals.
            </span>
          </p>
        </div>
      </div>
    </section>
  );
}
