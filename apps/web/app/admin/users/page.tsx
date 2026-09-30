import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminUsers } from "@/features/admin/components/users";

export const metadata: Metadata = { title: "Users" };

export default function AdminUsersPage() {
  return (
    <Suspense>
      <AdminUsers />
    </Suspense>
  );
}
