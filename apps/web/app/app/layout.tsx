import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { getCurrentUser } from "@/lib/api/server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Server-side gate: no session cookie → no shell, no flash of protected UI.
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return <AppShell user={user}>{children}</AppShell>;
}
