import type { Metadata } from "next";

import { AppearanceSettings } from "@/features/settings/components/appearance-settings";

export const metadata: Metadata = { title: "Appearance" };

export default function AppearanceSettingsPage() {
  return <AppearanceSettings />;
}
