import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { AdminReauth } from "@/features/admin/components/admin-reauth";
import { AdminShell } from "@/features/admin/components/admin-shell";
import { ApiError } from "@/lib/api/client";
import { getCurrentUser, serverApi } from "@/lib/api/server";

export const metadata: Metadata = { title: { default: "Admin", template: "%s · Admin · Notely AI" }, robots: { index: false, follow: false } };

/**
 * Server-side gate for /admin. The API is the authority (every /api/v1/admin call re-checks the
 * role); this gate only avoids rendering the console for people who can't use it:
 * signed out → sign in; not staff → 404 (the area isn't advertised); stale admin session or
 * missing 2FA → a sign-in-again screen.
 */
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login?next=/admin");
  if (!user.role || user.role === "user") notFound();
  try {
    await serverApi("/admin/me");
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.code === "ADMIN_REAUTH_REQUIRED") return <AdminShell user={user}><AdminReauth reason="reauth" /></AdminShell>;
      if (error.code === "ADMIN_2FA_REQUIRED") return <AdminShell user={user}><AdminReauth reason="two_factor" /></AdminShell>;
      if (error.status === 403) notFound();
      if (error.status === 401) redirect("/login?next=/admin");
    }
    throw error;
  }
  return <AdminShell user={user}>{children}</AdminShell>;
}
