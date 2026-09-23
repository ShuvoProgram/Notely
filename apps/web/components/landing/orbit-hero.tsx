"use client";

import Link from "next/link";
import * as React from "react";

import { ArrowDown, ArrowRight, CalendarDays, Check, Loader2, NotebookPen, Sparkles, type IconComponent } from "@/components/icons";
import { logoUrl } from "@/components/landing/content";
import { Magnetic } from "@/components/landing/magnetic";
import { EASE, MOTION_OK, gsap, useGSAP } from "@/components/landing/motion";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/*
 * The hero tells the product story around the headline:
 *
 *   NOTE ──▶ ASSISTANT ──▶ TASK ──▶ CALENDAR ──▶ (again)
 *
 * Four small, realistic Notely surfaces sit at the corners of a loop track that circles the copy.
 * A short signal travels the track from one card to the next and each card plays its step: the note
 * is active, the assistant proposes two tasks, ticks them and is approved, the task arrives, the
 * calendar syncs it. Nothing depends on the cursor. Under reduced motion every card simply shows
 * its finished state.
 *
 * Layout: the stage has a fixed, viewport-capped height (not an aspect ratio), and the cards are
 * placed by percentage *inside* it, so the whole composition always fits above the fold and nothing
 * is clipped. The track is an ellipse defined in stage percentages (the same ones that place the
 * cards) and drawn in the stage's measured pixels, so the signal's dash stays a single short arc.
 * From lg up; smaller screens get MiniFlow, the same four steps as compact cards under the copy.
 */

// Ellipse track in stage percentages. The cards sit where it crosses the four diagonals.
const RX = 45;
const RY = 43.3;
const round = (n: number, p = 3) => Math.round(n * 10 ** p) / 10 ** p;
const point = (deg: number) => ({ x: round(50 + RX * Math.cos((deg * Math.PI) / 180)), y: round(50 + RY * Math.sin((deg * Math.PI) / 180)) });

const START = 216.87; // the note's angle: the track (and the signal's path) starts here
const STOPS = { note: 0, assistant: (323.13 - START) / 360, task: (396.87 - START) / 360, calendar: (503.13 - START) / 360, end: 1 } as const;
const ANCHOR = { note: point(START), assistant: point(323.13), task: point(36.87), calendar: point(143.13) };

/**
 * One clockwise lap from the note, in real pixels for a stage of w×h. Drawn in pixels (not a
 * stretched 0–100 box) so the signal's dash stays one short arc: dashes along a non-uniformly
 * scaled path don't measure correctly.
 */
const trackPath = (w: number, h: number) =>
  Array.from({ length: 121 }, (_, i) => {
    const p = point(START + i * 3);
    return `${i ? "L" : "M"}${round((p.x / 100) * w, 1)} ${round((p.y / 100) * h, 1)}`;
  }).join(" ");

const READS = [
  { name: "Gmail", slug: "gmail" },
  { name: "Google Docs", slug: "googledocs" },
  { name: "Notion", slug: "notion" },
];

export function OrbitHero() {
  const root = React.useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const el = root.current;
      if (!el) return;
      const q = gsap.utils.selector(el);
      const mm = gsap.matchMedia();

      // Entrance: words rise, copy and CTAs follow, the track draws, the cards settle in.
      mm.add(MOTION_OK, () => {
        gsap
          .timeline({ defaults: { ease: EASE } })
          .fromTo(q("[data-hero-word]"), { yPercent: 110, opacity: 1 }, { yPercent: 0, duration: 1, ease: "power4.out", stagger: 0.07 })
          .fromTo(q("[data-hero-fade]"), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.8, stagger: 0.08 }, "-=0.6")
          .fromTo(q("[data-ring]"), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 1.6, ease: "power2.inOut", stagger: 0.12 }, 0.1)
          .fromTo(q("[data-pop]"), { opacity: 0, y: 16, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.8, stagger: 0.1 }, 0.45);
      });

      // The workflow loop (lg+, where the cards are shown). Paused while the hero is off-screen.
      mm.add(`${MOTION_OK} and (min-width: 1024px)`, () => {
        const signal = q("[data-signal]")[0] as SVGPathElement | undefined;
        if (!signal) return;
        const card = (k: string) => q(`[data-flow='${k}']`)[0];
        const note = card("note");
        const assistant = card("assistant");
        const task = card("task");
        const calendar = card("calendar");
        const apps = q("[data-read]");
        const all = [note, assistant, task, calendar];

        const LEN = 0.07;
        const s = { f: 0 };
        const place = () => (signal.style.strokeDashoffset = String(LEN - s.f));
        const flag = (node: Element | undefined, attr: string, on: boolean) => node?.toggleAttribute(attr, on);
        const active = (node: Element | undefined) => all.forEach((n) => flag(n, "data-active", n === node));
        const travel = (from: number, to: number, duration: number) =>
          gsap
            .timeline()
            .set(s, { f: from, onComplete: place })
            .to(signal, { opacity: 1, duration: 0.25 }, 0)
            .to(s, { f: to, duration, ease: "power1.inOut", onUpdate: place }, 0)
            .to(signal, { opacity: 0, duration: 0.3 }, ">-0.25");
        const reset = () => {
          active(undefined);
          ["data-c1", "data-c2", "data-approved"].forEach((a) => flag(assistant, a, false));
          flag(task, "data-new", false);
          flag(calendar, "data-synced", false);
          apps.forEach((a) => a.removeAttribute("data-live"));
        };
        reset();
        gsap.set(signal, { opacity: 0 });

        const loop = gsap.timeline({ repeat: -1, delay: 1.6, paused: true });
        // 1. The note.
        loop.call(reset).call(() => active(note)).to({}, { duration: 1.4 });
        // 2. → Assistant: it reads the note and connected apps, proposes, ticks, is approved.
        loop.add(travel(STOPS.note, STOPS.assistant, 1.5)).call(() => active(assistant), [], "-=0.2");
        apps.forEach((a, i) => loop.call(() => a.setAttribute("data-live", ""), [], i ? "+=0.3" : "+=0.2").call(() => a.removeAttribute("data-live"), [], "+=0.5"));
        loop
          .call(() => flag(assistant, "data-c1", true), [], "+=0.2")
          .call(() => flag(assistant, "data-c2", true), [], "+=0.55")
          .call(() => flag(assistant, "data-approved", true), [], "+=0.7")
          .to({}, { duration: 0.8 })
          // 3. → Task: created from the approval.
          .add(travel(STOPS.assistant, STOPS.task, 1.1))
          .call(() => {
            active(task);
            flag(task, "data-new", true);
          }, [], "-=0.2")
          .to({}, { duration: 1.4 })
          // 4. → Calendar: scheduled and synced.
          .add(travel(STOPS.task, STOPS.calendar, 1.5))
          .call(() => active(calendar), [], "-=0.2")
          .call(() => flag(calendar, "data-synced", true), [], "+=0.9")
          .to({}, { duration: 2 })
          // …and back round to the note.
          .add(travel(STOPS.calendar, STOPS.end, 1.2));

        const io = new IntersectionObserver(([entry]) => (entry?.isIntersecting ? loop.play() : loop.pause()));
        io.observe(el);
        return () => {
          io.disconnect();
          // The finished, static picture (reduced motion / below lg).
          reset();
          ["data-c1", "data-c2", "data-approved"].forEach((a) => flag(assistant, a, true));
          flag(task, "data-new", true);
          flag(calendar, "data-synced", true);
        };
      });

      return () => mm.revert();
    },
    { scope: root },
  );

  return (
    <section ref={root} aria-labelledby="hero-heading" className="landing-hero relative mx-auto w-full max-w-[1320px] px-4 pb-12 pt-10 sm:px-6 sm:pt-14 lg:h-[clamp(34rem,calc(100svh-7.5rem),40rem)] lg:px-0 lg:py-0">
      <Stage />

      {/* On lg the copy layer spans the stage; only its own content takes the pointer. */}
      <div className="relative z-10 mx-auto flex max-w-2xl flex-col items-center text-center lg:pointer-events-none lg:absolute lg:inset-0 lg:max-w-none lg:justify-center lg:[&>*]:pointer-events-auto">
        <p data-hero-fade className="landing-fade mb-4 inline-flex items-center gap-2 rounded-full bg-ai/10 px-3 py-1 text-xs font-bold text-ai ring-1 ring-ai/25 sm:text-sm">
          <Sparkles className="size-3.5" aria-hidden />
          The AI workspace for notes &amp; tasks
        </p>
        <h1 id="hero-heading" className="text-[clamp(2.6rem,10vw,4.25rem)] font-black leading-[0.98] tracking-[-0.045em] text-balance lg:max-w-[30rem] lg:text-[3.4rem] xl:max-w-[40rem] xl:text-[4.25rem]">
          <span className="sr-only">Think it. Ask it. Notely does the rest.</span>
          <span aria-hidden>
            <HeroLine words={["Think", "it."]} />
            <HeroLine words={["Ask", "it."]} />
            <HeroLine words={["Notely", "does", "the", "rest."]} accent />
          </span>
        </h1>
        <p data-hero-fade className="landing-fade mt-5 max-w-[30rem] text-base leading-relaxed text-foreground-secondary sm:text-lg lg:max-w-[26rem] lg:text-base xl:max-w-[30rem] xl:text-lg">
          Write it down. Notely’s assistant turns your notes into tasks and puts them on your calendar, with your approval at every step.
        </p>
        <div data-hero-fade className="landing-fade mt-7 flex w-full flex-col items-center gap-3 sm:w-auto sm:flex-row sm:gap-5">
          <Magnetic className="w-full sm:w-auto">
            <Button size="lg" asChild className="h-12 w-full rounded-xl bg-foreground px-6 text-base font-bold text-background shadow-[0_10px_30px_-12px_rgb(0_0_0/0.5)] hover:bg-foreground/90 sm:w-auto">
              <Link href="/signup">
                Create your workspace <ArrowRight aria-hidden />
              </Link>
            </Button>
          </Magnetic>
          <a href="#how-it-works" className="group inline-flex h-11 items-center gap-1.5 rounded-xl px-2 text-base font-bold text-foreground-secondary outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
            See how it works <ArrowDown className="size-4 transition-transform duration-300 group-hover:translate-y-0.5" aria-hidden />
          </a>
        </div>
      </div>

      <MiniFlow />
    </section>
  );
}

function HeroLine({ words, accent }: { words: string[]; accent?: boolean }) {
  return (
    <span className="block">
      {words.map((w, i) => (
        <React.Fragment key={i}>
          <span className="inline-block overflow-hidden pb-[0.1em] -mb-[0.1em] align-bottom">
            <span data-hero-word className={cn("inline-block will-change-transform", accent && i === 0 && "landing-mark")}>
              {w}
            </span>
          </span>
          {i < words.length - 1 ? " " : null}
        </React.Fragment>
      ))}
    </span>
  );
}

/* ──────────────────────────────── desktop stage ──────────────────────────────── */

/** Rings, the loop track with its signal, the four product cards and the apps the assistant reads. */
function Stage() {
  const top = point(270);
  // The stage's pixel size, so the track can be drawn without stretching (see trackPath).
  const ref = React.useRef<HTMLDivElement>(null);
  const [size, setSize] = React.useState({ w: 1320, h: 640 });
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => e && setSize({ w: Math.round(e.contentRect.width), h: Math.round(e.contentRect.height) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const track = trackPath(size.w, size.h);
  return (
    <div ref={ref} aria-hidden className="pointer-events-none absolute inset-0 hidden select-none lg:block">
      {/* Backdrop rings: purely atmospheric, faded out toward the edges instead of cut by them. */}
      <svg viewBox="0 0 1200 640" preserveAspectRatio="xMidYMid slice" className="landing-rings absolute inset-0 size-full text-foreground">
        {[230, 360].map((r) => (
          <circle key={r} data-ring cx={600} cy={320} r={r} pathLength={1} strokeDasharray="1 1" fill="none" stroke="currentColor" strokeOpacity={0.07} />
        ))}
      </svg>
      {/* The workflow track and the signal that runs along it. */}
      <svg viewBox={`0 0 ${size.w} ${size.h}`} className="absolute inset-0 size-full text-foreground">
        <path data-ring d={track} pathLength={1} strokeDasharray="1 1" fill="none" stroke="currentColor" strokeOpacity={0.14} strokeWidth={1} />
        <path data-signal d={track} pathLength={1} strokeDasharray="0.07 0.93" fill="none" stroke="var(--ai)" strokeWidth={2.5} strokeLinecap="round" className="landing-signal" opacity={0} />
      </svg>

      {/* Apps the assistant reads from, on the track between the note and the assistant. */}
      <div className="absolute flex -translate-x-1/2 -translate-y-1/2 gap-2" style={{ left: `${top.x}%`, top: `${top.y}%` }}>
        {READS.map((a) => (
          <span key={a.slug} data-read data-pop className="landing-app grid size-8 place-items-center rounded-full bg-white">
            {/* eslint-disable-next-line @next/next/no-img-element -- tiny vendor SVGs from the marketplace's logo CDN */}
            <img src={logoUrl(a.slug)} alt="" width={16} height={16} loading="lazy" decoding="async" className="size-4" />
          </span>
        ))}
      </div>

      <FlowCard at={ANCHOR.note} kind="note" icon={NotebookPen} label="Note" meta="Edited now">
        <p className="text-[15px] font-bold leading-tight">Q3 launch plan</p>
        <ul className="mt-2 space-y-1 text-[12px] text-foreground-secondary">
          {["Launch timeline", "Product updates", "Marketing priorities"].map((l) => (
            <li key={l} className="flex items-center gap-1.5">
              <span className="size-1 rounded-full bg-foreground/40" />
              {l}
            </li>
          ))}
        </ul>
        <span className="mt-2.5 inline-flex rounded-full bg-foreground/[0.06] px-2 py-0.5 font-mono text-[10px] text-muted-foreground">#launch</span>
      </FlowCard>

      <FlowCard at={ANCHOR.assistant} kind="assistant" icon={Sparkles} label="Assistant" accent>
        <p className="text-[13px] font-medium leading-snug">Create 2 tasks from “Q3 launch plan”</p>
        <ul className="mt-2 space-y-1.5 text-[12px]">
          <CheckRow n={1}>Review launch requirements</CheckRow>
          <CheckRow n={2}>Prepare launch announcement</CheckRow>
        </ul>
        <span className="landing-approve mt-2.5 inline-flex h-6 items-center gap-1 rounded-md px-2 text-[11px] font-bold">
          <span className="landing-when-pending">Approve</span>
          <span className="landing-when-approved inline-flex items-center gap-1">
            <Check className="size-3" aria-hidden /> Approved
          </span>
        </span>
      </FlowCard>

      <FlowCard at={ANCHOR.task} kind="task" icon={TaskBox} label="Task" meta={<span className="landing-when-new text-ai">From assistant</span>}>
        <p className="text-[15px] font-bold leading-tight">Send pricing proposal</p>
        <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1 font-medium text-warning">
            <span className="size-1.5 rounded-full bg-warning" /> High
          </span>
          <span>Today · 3:30 PM</span>
        </p>
      </FlowCard>

      <FlowCard at={ANCHOR.calendar} kind="calendar" icon={CalendarDays} label="Google Calendar">
        <div className="flex gap-2.5">
          <div className="landing-event w-1 shrink-0 rounded-full" />
          <div>
            <p className="text-[15px] font-bold leading-tight">Pricing proposal</p>
            <p className="mt-1 text-[11px] text-muted-foreground">Today · 3:30 – 4:00 PM</p>
          </div>
        </div>
        <p className="mt-2.5 flex items-center gap-1 text-[11px] font-bold">
          <span className="landing-when-syncing inline-flex items-center gap-1 text-muted-foreground">
            <Loader2 className="size-3 animate-spin" aria-hidden /> Syncing
          </span>
          <span className="landing-when-synced inline-flex items-center gap-1 text-ai">
            <Check className="size-3" aria-hidden /> Synced
          </span>
        </p>
      </FlowCard>
    </div>
  );
}

function TaskBox({ className }: { className?: string }) {
  return (
    <span className={cn("landing-taskbox grid place-items-center rounded-[4px] border-[1.5px] border-current", className)}>
      <Check className="size-2.5" aria-hidden />
    </span>
  );
}

function CheckRow({ n, children }: { n: 1 | 2; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2">
      <span data-check={n} className="landing-check grid size-4 shrink-0 place-items-center rounded-full border border-foreground/25">
        <Check className="size-2.5" aria-hidden />
      </span>
      {children}
    </li>
  );
}

function FlowCard({
  at,
  kind,
  icon: Icon,
  label,
  meta,
  accent,
  children,
}: {
  at: { x: number; y: number };
  kind: string;
  icon: IconComponent | ((p: { className?: string }) => React.ReactNode);
  label: string;
  meta?: React.ReactNode;
  accent?: boolean;
  children: React.ReactNode;
}) {
  // Finished state by default (what reduced motion and the first paint show); the loop resets it.
  const done = kind === "assistant" ? { "data-c1": "", "data-c2": "", "data-approved": "" } : kind === "task" ? { "data-new": "" } : kind === "calendar" ? { "data-synced": "" } : {};
  return (
    <div className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${at.x}%`, top: `${at.y}%` }}>
      <div data-pop>
        <div data-flow={kind} {...done} className="landing-flowcard w-[208px] rounded-2xl bg-card p-3.5 text-left xl:w-[224px]">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className={cn("flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground [&_svg]:size-3.5", accent && "text-ai")}>
              <Icon className="size-3.5" />
              {label}
            </p>
            {meta ? <span className="text-[10px] font-medium text-muted-foreground">{meta}</span> : null}
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────── below lg ──────────────────────────────── */

const MINI: { icon: IconComponent; label: string; title: string; detail: string }[] = [
  { icon: NotebookPen, label: "Note", title: "Q3 launch plan", detail: "#launch" },
  { icon: Sparkles, label: "Assistant", title: "Create 2 tasks", detail: "Approved" },
  { icon: Check, label: "Task", title: "Send pricing proposal", detail: "High · Today" },
  { icon: CalendarDays, label: "Calendar", title: "Pricing proposal", detail: "3:30 – 4:00 PM" },
];

/** The same four steps as compact cards in reading order, with the active step moving through them. */
function MiniFlow() {
  const ref = React.useRef<HTMLOListElement>(null);
  useGSAP(
    () => {
      const el = ref.current;
      if (!el) return;
      const mm = gsap.matchMedia();
      mm.add(`${MOTION_OK} and (max-width: 1023px)`, () => {
        const items = gsap.utils.toArray<HTMLElement>(el.querySelectorAll("li"));
        const tl = gsap.timeline({ repeat: -1, repeatDelay: 0.8, paused: true });
        items.forEach((li) => {
          tl.call(() => items.forEach((x) => x.toggleAttribute("data-active", x === li)))
            .fromTo(li, { y: 0 }, { y: -3, duration: 0.3, ease: "power2.out", yoyo: true, repeat: 1 })
            .to({}, { duration: 1.1 });
        });
        const io = new IntersectionObserver(([e]) => (e?.isIntersecting ? tl.play() : tl.pause()));
        io.observe(el);
        return () => {
          io.disconnect();
          items.forEach((x) => x.removeAttribute("data-active"));
        };
      });
      return () => mm.revert();
    },
    { scope: ref },
  );

  return (
    <ol ref={ref} aria-label="How Notely works: note, assistant, task, calendar" data-hero-fade className="landing-fade relative z-10 mx-auto mt-10 grid max-w-md grid-cols-2 gap-2.5 md:max-w-3xl md:grid-cols-4 lg:hidden">
      {MINI.map((m, i) => (
        <li key={m.label} className="landing-flowcard relative rounded-2xl bg-card p-3 text-left">
          <p className="flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            <m.icon className="size-3.5" aria-hidden />
            <span className="text-foreground/40">{i + 1}</span> {m.label}
          </p>
          <p className="mt-1.5 truncate text-sm font-bold">{m.title}</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{m.detail}</p>
        </li>
      ))}
    </ol>
  );
}
