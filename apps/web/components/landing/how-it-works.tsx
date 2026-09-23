"use client";

import * as React from "react";

import { CalendarCheck, Check, FileText, NotebookPen, Sparkles, Tag } from "@/components/icons";
import { STEPS, type StepKey } from "@/components/landing/content";
import { EASE, MOTION_OK, ScrollTrigger, gsap, useGSAP } from "@/components/landing/motion";
import { SectionLabel, Words } from "@/components/landing/reveal";
import { cn } from "@/lib/utils";

/*
 * Four steps, told with the product's own surfaces. On lg+ the visual is sticky and swaps as each
 * step crosses the middle of the viewport, while a progress rail fills with the scroll. On smaller
 * screens each step simply carries its own visual underneath it (no sticky, no scrubbing).
 */
export function HowItWorks() {
  const root = React.useRef<HTMLElement>(null);
  const [active, setActive] = React.useState(0);

  useGSAP(
    () => {
      const el = root.current;
      if (!el) return;
      const q = gsap.utils.selector(el);
      const mm = gsap.matchMedia();

      // Which step is "current" drives the sticky visual. Runs regardless of motion preference.
      mm.add("(min-width: 1024px)", () => {
        q("[data-step]").forEach((step, i) =>
          ScrollTrigger.create({ trigger: step, start: "top 55%", end: "bottom 55%", onToggle: (self) => self.isActive && setActive(i) }),
        );
      });

      mm.add(`${MOTION_OK} and (min-width: 1024px)`, () => {
        gsap.fromTo(q("[data-rail-fill]"), { scaleY: 0 }, { scaleY: 1, ease: "none", scrollTrigger: { trigger: q("[data-steps]")[0], start: "top 55%", end: "bottom 55%", scrub: 0.4 } });
      });
    },
    { scope: root },
  );

  return (
    <section ref={root} id="how-it-works" aria-labelledby="how-heading" className="scroll-mt-20 border-t border-foreground/10">
      <div className="mx-auto w-full max-w-6xl px-4 pb-20 pt-14 sm:px-6 lg:pb-28 lg:pt-16">
        <SectionLabel index="01">How it works</SectionLabel>
        <h2 id="how-heading" data-reveal="words" className="mt-5 max-w-3xl text-[clamp(2.25rem,5.5vw,4rem)] font-black leading-[0.98] tracking-[-0.04em]">
          <Words text="From a messy note to a scheduled task. With you in charge." />
        </h2>

        <div className="mt-14 grid gap-12 lg:mt-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-16">
          <ol data-steps className="relative lg:pl-10">
            <span aria-hidden className="absolute bottom-0 left-0 top-0 hidden w-px bg-foreground/15 lg:block">
              <span data-rail-fill className="block h-full w-full origin-top bg-ai" />
            </span>
            {STEPS.map((s, i) => (
              <li key={s.key} data-step className="lg:flex lg:min-h-[52vh] lg:flex-col lg:justify-center [&+&]:mt-14 lg:[&+&]:mt-0">
                <div data-reveal>
                <div className={cn("transition-opacity duration-500 lg:opacity-40", active === i && "lg:opacity-100")}>
                  <p className="font-mono text-sm text-ai">{String(i + 1).padStart(2, "0")}</p>
                  <h3 className="mt-2 text-3xl font-black tracking-[-0.03em] sm:text-4xl">{s.title}</h3>
                  <p className="mt-3 max-w-md text-base leading-relaxed text-foreground-secondary sm:text-lg">{s.body}</p>
                </div>
                </div>
                <div className="mt-6 lg:hidden" data-reveal>
                  <StepVisual step={s.key} active />
                </div>
              </li>
            ))}
          </ol>

          <div className="hidden lg:block">
            <div className="sticky top-[calc(50vh-13rem)] h-[26rem]">
              {STEPS.map((s, i) => (
                <div
                  key={s.key}
                  aria-hidden={active !== i}
                  className={cn(
                    "absolute inset-0 transition-[opacity,transform] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none",
                    active === i ? "translate-y-0 opacity-100" : i < active ? "-translate-y-6 opacity-0" : "translate-y-6 opacity-0",
                  )}
                >
                  <StepVisual step={s.key} active={active === i} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/** A product surface per step. When it becomes active its parts assemble in order. */
function StepVisual({ step, active }: { step: StepKey; active: boolean }) {
  const ref = React.useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      if (!active || !ref.current) return;
      const mm = gsap.matchMedia();
      mm.add(MOTION_OK, () => {
        gsap.fromTo(ref.current!.querySelectorAll("[data-part]"), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.55, ease: EASE, stagger: 0.09, delay: 0.1 });
      });
      return () => mm.revert();
    },
    { dependencies: [active], scope: ref },
  );

  return (
    <div ref={ref} className="landing-panel h-full border border-foreground/15 bg-background p-5 sm:p-6">
      {step === "capture" ? <CaptureVisual /> : step === "ask" ? <AskVisual /> : step === "approve" ? <ApproveVisual /> : <DoneVisual />}
    </div>
  );
}

const Mono = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <p className={cn("font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground", className)}>{children}</p>
);

function CaptureVisual() {
  return (
    <div className="flex h-full flex-col">
      <div data-part className="flex items-center justify-between border-b border-foreground/10 pb-3">
        <Mono className="flex items-center gap-2">
          <NotebookPen className="size-3.5" aria-hidden /> Notes / Launch
        </Mono>
        <span className="font-mono text-[11px] text-muted-foreground">Saved</span>
      </div>
      <p data-part className="mt-5 text-2xl font-black tracking-tight">Q3 launch plan</p>
      <ul className="mt-4 space-y-2.5 text-[15px] text-foreground-secondary">
        <li data-part>– Pricing page goes live on the 1st</li>
        <li data-part>– Send the pricing proposal to Dana by Friday</li>
        <li data-part>– Draft the launch email</li>
      </ul>
      <div data-part className="mt-auto flex flex-wrap gap-2 pt-5">
        {["launch", "q3", "pricing"].map((t) => (
          <span key={t} className="inline-flex items-center gap-1 border border-foreground/15 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
            <Tag className="size-3" aria-hidden />
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

function AskVisual() {
  return (
    <div className="flex h-full flex-col gap-4">
      <Mono>
        <span data-part className="inline-flex items-center gap-2">
          <Sparkles className="size-3.5 text-ai" aria-hidden /> Assistant
        </span>
      </Mono>
      <p data-part className="ml-auto max-w-[80%] bg-foreground px-4 py-3 text-[15px] font-medium text-background">What’s still open for the Q3 launch?</p>
      <div data-part className="max-w-[88%] border border-foreground/15 px-4 py-3 text-[15px] leading-relaxed">
        Two things: the pricing proposal for Dana (due Friday) and the launch email draft. Want me to turn them into tasks?
      </div>
      <div data-part className="mt-auto flex flex-wrap gap-2">
        <Mono className="w-full">Sources</Mono>
        {["Q3 launch plan", "Pricing notes"].map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5 border border-foreground/15 px-2 py-1 text-xs">
            <FileText className="size-3.5" aria-hidden /> {s}
          </span>
        ))}
      </div>
    </div>
  );
}

function ApproveVisual() {
  const rows = [
    { title: "Create task", detail: "Send pricing proposal · Fri 3:30 PM", done: true },
    { title: "Create task", detail: "Draft the launch email · Mon", done: false },
  ];
  return (
    <div className="flex h-full flex-col">
      <div data-part className="flex items-center justify-between">
        <Mono className="text-ai">Needs your approval</Mono>
        <span className="font-mono text-[11px] text-muted-foreground">Step 2 of 2</span>
      </div>
      <ul className="mt-4 divide-y divide-foreground/10 border-y border-foreground/10">
        {rows.map((r) => (
          <li key={r.detail} data-part className="flex items-center gap-3 py-3.5">
            <span className={cn("grid size-5 shrink-0 place-items-center border", r.done ? "border-ai bg-ai text-primary-foreground" : "border-foreground/40")}>
              {r.done ? <Check className="size-3.5" aria-hidden /> : null}
            </span>
            <span className="min-w-0">
              <span className="block text-[15px] font-bold">{r.title}</span>
              <span className="block truncate text-sm text-muted-foreground">{r.detail}</span>
            </span>
          </li>
        ))}
      </ul>
      <div data-part className="mt-auto flex items-center gap-2 pt-5">
        <span className="inline-flex h-10 items-center bg-primary px-4 text-sm font-bold text-primary-foreground">Approve</span>
        <span className="inline-flex h-10 items-center border border-foreground/20 px-4 text-sm font-medium">Skip</span>
        <span className="ml-auto text-xs text-muted-foreground">Nothing runs until you say so.</span>
      </div>
    </div>
  );
}

function DoneVisual() {
  const tasks = [
    { t: "Send pricing proposal", d: "Fri · 3:30 PM", cal: true },
    { t: "Draft the launch email", d: "Mon", cal: false },
  ];
  return (
    <div className="flex h-full flex-col">
      <Mono>
        <span data-part>Tasks · This week</span>
      </Mono>
      <ul className="mt-4 space-y-2">
        {tasks.map((x) => (
          <li key={x.t} data-part className="flex items-center gap-3 border border-foreground/15 px-3.5 py-3">
            <span className="size-4 shrink-0 border border-foreground/40" />
            <span className="min-w-0 flex-1">
              <span className="block text-[15px] font-bold">{x.t}</span>
              <span className="block font-mono text-xs text-muted-foreground">{x.d}</span>
            </span>
            {x.cal ? (
              <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-wider text-ai">
                <CalendarCheck className="size-3.5" aria-hidden /> In calendar
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <div data-part className="mt-auto border-t border-foreground/10 pt-4">
        <Mono>Automation</Mono>
        <p className="mt-1.5 text-[15px] font-medium">Every Monday 9:00 — summarise open launch tasks into a note.</p>
      </div>
    </div>
  );
}
