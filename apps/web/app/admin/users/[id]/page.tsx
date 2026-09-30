import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AdminUserDetailView } from "@/features/admin/components/user-detail";

export const metadata: Metadata = { title: "User" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function AdminUserPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  return <AdminUserDetailView id={id} />;
}
