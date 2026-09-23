"use client";

import * as React from "react";

import { useCurrentUser } from "@/features/auth/hooks";
import { applyLook, forgetRetiredStorage } from "@/lib/appearance/apply";
import { DEFAULT_APPEARANCE, resolve } from "@/lib/appearance/model";
import type { Appearance, User } from "@/lib/api/types";

/**
 * Applies the signed-in user's saved look, so it follows them across devices and survives
 * sign-out/sign-in. The settings page previews changes itself; once they're saved this picks up
 * the same values. Renders nothing.
 */
export function AppearanceSync({ initialUser }: { initialUser: User }) {
  const { data: user = initialUser } = useCurrentUser(initialUser);
  const key = JSON.stringify(user.appearance ?? DEFAULT_APPEARANCE);
  React.useEffect(() => {
    applyLook(resolve(JSON.parse(key) as Appearance));
  }, [key]);
  React.useEffect(() => forgetRetiredStorage(), []);
  return null;
}

/** The picture behind the app, and the scrim that keeps text on top of it readable. */
export function AppBackdrop() {
  return (
    <div aria-hidden className="app-backdrop">
      <div className="app-scrim" />
    </div>
  );
}
