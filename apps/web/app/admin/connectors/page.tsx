import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminConnectors } from "@/features/admin/components/connectors";

export const metadata: Metadata = { title: "Connectors" };

export default function AdminConnectorsPage() {
  return (
    <Suspense>
      <AdminConnectors />
    </Suspense>
  );
}
