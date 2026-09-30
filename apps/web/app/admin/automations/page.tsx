import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminAutomations } from "@/features/admin/components/automations";

export const metadata: Metadata = { title: "Automations" };

export default function AdminAutomationsPage() {
  return (
    <Suspense>
      <AdminAutomations />
    </Suspense>
  );
}
