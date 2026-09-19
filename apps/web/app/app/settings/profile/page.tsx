import type { Metadata } from "next";

import { ProfileForm } from "@/features/settings/components/profile-form";

export const metadata: Metadata = { title: "Profile" };

export default function ProfileSettingsPage() {
  return <ProfileForm />;
}
