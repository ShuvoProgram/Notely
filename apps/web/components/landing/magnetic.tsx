"use client";

import * as React from "react";

import { FINE_POINTER, MOTION_OK, gsap, useGSAP } from "@/components/landing/motion";
import { cn } from "@/lib/utils";

/**
 * Pulls its child a few pixels toward the cursor and springs back on leave, and gives a small
 * press on click, so the primary CTAs answer the pointer. Mouse only, never under reduced motion.
 */
export function Magnetic({ children, strength = 0.28, className }: { children: React.ReactNode; strength?: number; className?: string }) {
  const ref = React.useRef<HTMLSpanElement>(null);

  useGSAP(
    () => {
      const el = ref.current;
      if (!el) return;
      const mm = gsap.matchMedia();
      mm.add(`${MOTION_OK} and ${FINE_POINTER}`, () => {
        const x = gsap.quickTo(el, "x", { duration: 0.5, ease: "power3.out" });
        const y = gsap.quickTo(el, "y", { duration: 0.5, ease: "power3.out" });
        const move = (e: PointerEvent) => {
          const r = el.getBoundingClientRect();
          x((e.clientX - (r.left + r.width / 2)) * strength);
          y((e.clientY - (r.top + r.height / 2)) * strength);
        };
        const leave = () => {
          x(0);
          y(0);
        };
        const press = () => gsap.fromTo(el, { scale: 0.96 }, { scale: 1, duration: 0.45, ease: "elastic.out(1, 0.5)" });
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerleave", leave);
        el.addEventListener("pointerdown", press);
        return () => {
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerleave", leave);
          el.removeEventListener("pointerdown", press);
        };
      });
      return () => mm.revert();
    },
    { scope: ref },
  );

  return (
    <span ref={ref} className={cn("inline-flex will-change-transform", className)}>
      {children}
    </span>
  );
}
