import type { Metadata } from "next";

import { AdminSettingsView } from "@/features/admin/components/settings";

export const metadata: Metadata = { title: "Settings" };

export default function AdminSettingsPage() {
  return <AdminSettingsView />;
}
