import type { Metadata } from "next";
import { Suspense } from "react";

import { ProviderDetail } from "@/features/connections/components/provider-detail";

export const metadata: Metadata = { title: "Connection" };

export default async function ProviderPage({ params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  return (
    <div data-wide>
      <Suspense>
        <ProviderDetail providerId={provider} />
      </Suspense>
    </div>
  );
}
