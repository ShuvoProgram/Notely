import type { Metadata } from "next";

import { Marketplace } from "@/features/connections/components/marketplace";

export const metadata: Metadata = { title: "Connections" };

export default function ConnectionsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Connections</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect the apps you work in. The assistant can then search them and, with your approval, act in them.
        </p>
      </div>
      <Marketplace />
    </div>
  );
}
