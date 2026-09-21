import type { Metadata } from "next";

import { NotificationSettings } from "@/features/settings/components/notification-settings";

export const metadata: Metadata = { title: "Notifications" };

export default function NotificationSettingsPage() {
  return <NotificationSettings />;
}
