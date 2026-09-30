import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminOverview } from "@/features/admin/components/overview";

export const metadata: Metadata = { title: "Overview" };

export default function AdminOverviewPage() {
  return (
    <Suspense>
      <AdminOverview />
    </Suspense>
  );
}
