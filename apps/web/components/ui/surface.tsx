"use client";

import * as React from "react";

/**
 * Which glass layer the current subtree sits on. Floating layers (popovers, menus, selects)
 * portal to <body>, so they can't inherit styles from where they were opened; they read this
 * instead. Anything opened from inside a dialog takes the dialog's surface, radius and ring, so a
 * date or time picker reads as part of the dialog rather than a separate floating panel.
 */
export type SurfaceLevel = "page" | "dialog";

const SurfaceContext = React.createContext<SurfaceLevel>("page");

export function SurfaceProvider({ level, children }: { level: SurfaceLevel; children: React.ReactNode }) {
  return <SurfaceContext.Provider value={level}>{children}</SurfaceContext.Provider>;
}

export const useSurfaceLevel = () => React.useContext(SurfaceContext);

/** Classes for a floating layer: its own elevated glass, or the dialog's when opened from one. */
export function floatingSurface(level: SurfaceLevel): string {
  return level === "dialog" ? "glass-3 rounded-2xl ring-1 ring-glass-border-strong" : "glass-2 rounded-xl";
}
