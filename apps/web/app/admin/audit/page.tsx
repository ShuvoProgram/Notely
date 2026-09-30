import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminAuditLog } from "@/features/admin/components/audit-log";

export const metadata: Metadata = { title: "Audit log" };

export default function AdminAuditPage() {
  return (
    <Suspense>
      <AdminAuditLog />
    </Suspense>
  );
}
