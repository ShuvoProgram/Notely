import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminAIUsage } from "@/features/admin/components/ai-usage";

export const metadata: Metadata = { title: "AI usage" };

export default function AdminAIPage() {
  return (
    <Suspense>
      <AdminAIUsage />
    </Suspense>
  );
}
