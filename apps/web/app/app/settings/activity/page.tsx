import type { Metadata } from "next";

import { ActivityLog } from "@/features/ai/components/activity-log";
import { ChangeHistory } from "@/features/history/components/change-history";

export const metadata: Metadata = { title: "Activity" };

export default function ActivityPage() {
  return (
    <div className="space-y-6">
      <ChangeHistory />
      <ActivityLog />
    </div>
  );
}
