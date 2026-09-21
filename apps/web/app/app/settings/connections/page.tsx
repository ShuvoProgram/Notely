import type { Metadata } from "next";
import { Suspense } from "react";

import { Marketplace } from "@/features/connections/components/marketplace";

export const metadata: Metadata = { title: "Connections" };

export default function ConnectionsSettingsPage() {
  return (
    <div data-wide className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Connections</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Bring the apps you work in into Notely. The assistant can search them and, only with your approval, act in them. Connecting is one click — you authorize on the vendor&apos;s own screen.
        </p>
      </div>
      <Suspense>
        <Marketplace />
      </Suspense>
    </div>
  );
}
