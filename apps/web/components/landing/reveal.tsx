"use client";

import * as React from "react";

import { EASE, MOTION_OK, ScrollTrigger, gsap, useGSAP } from "@/components/landing/motion";
import { cn } from "@/lib/utils";

/**
 * Page-wide scroll reveals, mounted once. Markup opts in with attributes instead of wrappers:
 *   data-reveal         fades + rises into place as it enters the viewport (batched, staggered)
 *   data-reveal="words" a <Words> headline whose words rise out of their line boxes
 * CSS hides these before hydration (see landing.css) so nothing flashes; under reduced motion the
 * CSS never hides them and this does nothing.
 */
export function RevealOnScroll() {
  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add(MOTION_OK, () => {
      const blocks = gsap.utils.toArray<HTMLElement>("[data-reveal]:not([data-reveal='words'])");
      gsap.set(blocks, { y: 28 });
      ScrollTrigger.batch(blocks, {
        start: "top 97%",
        once: true,
        onEnter: (batch) => gsap.to(batch, { opacity: 1, y: 0, duration: 0.8, ease: EASE, stagger: 0.08, overwrite: true }),
      });

      for (const heading of gsap.utils.toArray<HTMLElement>("[data-reveal='words']")) {
        const words = heading.querySelectorAll("[data-word]");
        gsap.set(heading, { opacity: 1 });
        gsap.from(words, {
          yPercent: 110,
          duration: 0.9,
          ease: "power4.out",
          stagger: 0.06,
          scrollTrigger: { trigger: heading, start: "top 97%", once: true },
        });
      }
    });
    return () => mm.revert();
  });

  // In-page anchors glide to their section (only those, never the page's own scrolling, which a
  // global scroll-behavior would affect) and jump when motion is reduced.
  React.useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.("a[href^='#']");
      const id = a?.getAttribute("href")?.slice(1);
      const target = id ? document.getElementById(id) : null;
      if (!target || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: window.matchMedia(MOTION_OK).matches ? "smooth" : "auto" });
      history.replaceState(null, "", `#${id}`);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);
  return null;
}

/** Splits a heading into words, each in its own clipping box, for the word-rise reveal. */
export function Words({ text, className }: { text: string; className?: string }) {
  const words = text.split(" ");
  return (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden className={className}>
        {words.map((w, i) => (
          <React.Fragment key={i}>
            <span className="inline-block overflow-hidden pb-[0.12em] -mb-[0.12em] align-bottom">
              <span data-word className="inline-block will-change-transform">
                {w}
              </span>
            </span>
            {i < words.length - 1 ? " " : null}
          </React.Fragment>
        ))}
      </span>
    </>
  );
}

/** Mono section label: "01 / How it works". */
export function SectionLabel({ index, inverse, children }: { index: string; inverse?: boolean; children: React.ReactNode }) {
  return (
    <p data-reveal className={cn("flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em]", inverse ? "text-background/70" : "text-muted-foreground")}>
      <span className="text-ai">{index}</span>
      <span aria-hidden className={cn("h-px w-8", inverse ? "bg-background/30" : "bg-foreground/25")} />
      {children}
    </p>
  );
}
