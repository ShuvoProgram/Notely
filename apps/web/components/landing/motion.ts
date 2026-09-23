"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

/*
 * One place that registers GSAP for the landing page. Every animation goes through
 * `gsap.matchMedia()` with MOTION_OK, so with prefers-reduced-motion the page renders its final
 * state and nothing moves.
 */
gsap.registerPlugin(useGSAP, ScrollTrigger);

export const MOTION_OK = "(prefers-reduced-motion: no-preference)";
export const FINE_POINTER = "(hover: hover) and (pointer: fine)";
export const EASE = "power3.out";

export { gsap, ScrollTrigger, useGSAP };
