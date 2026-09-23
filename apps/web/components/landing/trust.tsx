import Link from "next/link";

import { ArrowRight, History, KeyRound, Lock, ShieldCheck, type IconComponent } from "@/components/icons";
import { Magnetic } from "@/components/landing/magnetic";
import { SectionLabel, Words } from "@/components/landing/reveal";
import { Button } from "@/components/ui/button";

// Each promise is something the product enforces in code, not a marketing claim.
const PROMISES: { icon: IconComponent; title: string; body: string }[] = [
  { icon: ShieldCheck, title: "You approve every change", body: "The assistant proposes; each step waits for you. Skip what you don’t want." },
  { icon: History, title: "A record of what it did", body: "An activity log records every action the assistant runs, and when." },
  { icon: Lock, title: "Credentials encrypted at rest", body: "App connections and your own AI keys are stored encrypted and never sent back to the browser." },
  { icon: KeyRound, title: "Two-factor sign-in", body: "Add an authenticator app, and see or sign out your other sessions any time." },
];

export function Trust() {
  return (
    <section id="trust" aria-labelledby="trust-heading" className="scroll-mt-20 border-t border-foreground/10 bg-foreground text-background">
      <div className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 lg:py-28">
        <SectionLabel index="04" inverse>
          Trust
        </SectionLabel>
        <h2 id="trust-heading" data-reveal="words" className="mt-5 max-w-4xl text-[clamp(2.25rem,5.5vw,4rem)] font-black leading-[0.98] tracking-[-0.04em]">
          <Words text="Powerful AI. Your hand on the switch." />
        </h2>
        <ul className="mt-14 grid gap-px bg-background/20 sm:grid-cols-2">
          {PROMISES.map((p) => (
            <li key={p.title} data-reveal className="group flex gap-4 bg-foreground p-6 sm:p-7">
              <p.icon className="mt-1 size-6 shrink-0 text-ai transition-transform duration-300 group-hover:scale-110" aria-hidden />
              <div>
                <h3 className="text-xl font-black tracking-[-0.02em]">{p.title}</h3>
                <p className="mt-1.5 text-[15px] leading-relaxed text-background/75">{p.body}</p>
              </div>
            </li>
          ))}
        </ul>
        <p data-reveal className="mt-8 text-sm text-background/70">
          Read the plain-language{" "}
          <Link href="/privacy-policy" className="font-medium text-background underline underline-offset-4 hover:text-ai">
            Privacy Policy
          </Link>{" "}
          and{" "}
          <Link href="/terms-and-conditions" className="font-medium text-background underline underline-offset-4 hover:text-ai">
            Terms
          </Link>
          .
        </p>
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section aria-labelledby="cta-heading" className="border-t border-foreground/10">
      <div className="mx-auto flex w-full max-w-6xl flex-col items-start gap-10 px-4 py-24 sm:px-6 lg:flex-row lg:items-end lg:justify-between lg:py-32">
        <h2 id="cta-heading" data-reveal="words" className="max-w-3xl text-[clamp(3rem,9vw,7rem)] font-black leading-[0.9] tracking-[-0.05em]">
          <Words text="Start with one note." />
        </h2>
        <div data-reveal className="flex flex-col items-start gap-4">
          <Magnetic>
            <Button size="lg" asChild className="h-14 rounded-xl bg-foreground px-8 text-lg font-bold text-background hover:bg-foreground/90">
              <Link href="/signup">
                Create your workspace <ArrowRight aria-hidden />
              </Link>
            </Button>
          </Magnetic>
          <p className="text-sm text-muted-foreground">
            Already using Notely?{" "}
            <Link href="/login" className="font-medium text-foreground underline underline-offset-4 hover:text-ai">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}
