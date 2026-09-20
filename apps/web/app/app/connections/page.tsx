import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Marketplace } from "@/features/connections/components/marketplace";

export const metadata: Metadata = { title: "Connections" };

export default function ConnectionsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Integrations"
        title="Connect your tools"
        description="Bring the apps you work in into Notely. The assistant can search them and, only with your approval, act in them. Connecting is one click — you authorize on the vendor's own screen."
      />
      <Suspense>
        <Marketplace />
      </Suspense>
    </div>
  );
}
