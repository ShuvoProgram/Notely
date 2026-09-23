import type { Metadata } from "next";

import { ChangePasswordForm } from "@/features/settings/components/change-password-form";
import { SessionsList } from "@/features/settings/components/sessions-list";
import { TwoFactorCard } from "@/features/settings/components/two-factor-card";

export const metadata: Metadata = { title: "Security" };

export default function SecuritySettingsPage() {
  return (
    <div className="space-y-8">
      <ChangePasswordForm />
      <TwoFactorCard />
      <SessionsList />
    </div>
  );
}
