import type { Metadata } from "next";

import { NotificationSettings } from "@/features/settings/components/notification-settings";
import { SoundSettings } from "@/features/settings/components/sound-settings";

export const metadata: Metadata = { title: "Notifications" };

export default function NotificationSettingsPage() {
  return (
    <div className="space-y-6">
      <NotificationSettings />
      <SoundSettings />
    </div>
  );
}
