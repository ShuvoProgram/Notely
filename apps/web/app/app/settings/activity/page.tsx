import type { Metadata } from "next";

import { ActivityLog } from "@/features/ai/components/activity-log";

export const metadata: Metadata = { title: "Activity" };

export default function ActivityPage() {
  return <ActivityLog />;
}
