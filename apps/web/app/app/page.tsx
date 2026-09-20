import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { HomeDashboard } from "@/features/home/components/home-dashboard";
import { getCurrentUser } from "@/lib/api/server";

export const metadata: Metadata = { title: "Home" };

export default async function AppHomePage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return <HomeDashboard user={user} />;
}
