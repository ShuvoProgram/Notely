"use client";

import * as React from "react";

import { useCurrentUser } from "@/features/auth/hooks";
import { sfx } from "@/lib/sfx/player";
import type { User } from "@/lib/api/types";

/**
 * Keeps the player's preference in step with the signed-in user, so the setting follows them
 * across devices and survives sign-out/sign-in. Renders nothing.
 */
export function SfxPreferenceSync({ initialUser }: { initialUser: User }) {
  const { data: user = initialUser } = useCurrentUser(initialUser);
  const { enabled, volume } = user.sound ?? { enabled: true, volume: 0.6 };
  React.useEffect(() => {
    sfx.configure({ enabled, volume });
    sfx.warm(["save", "success", "check"]);
  }, [enabled, volume]);
  return null;
}
