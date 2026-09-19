import type { Metadata } from "next";

import { AISettingsForm } from "@/features/ai/components/ai-settings-form";

export const metadata: Metadata = { title: "AI settings" };

export default function AISettingsPage() {
  return <AISettingsForm />;
}
