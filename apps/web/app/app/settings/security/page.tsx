import type { Metadata } from "next";

import { ChangePasswordForm } from "@/features/settings/components/change-password-form";
import { SessionsList } from "@/features/settings/components/sessions-list";

export const metadata: Metadata = { title: "Security" };

export default function SecuritySettingsPage() {
  return (
    <div className="space-y-8">
      <ChangePasswordForm />
      <SessionsList />
    </div>
  );
}
