"use client";

import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useCurrentUser, useUpdateProfile } from "@/features/auth/hooks";

// Mirrors PREF_FOR_KIND in apps/api/app/services/notification_service.py.
const GROUPS: { key: string; label: string; description: string }[] = [
  { key: "task_reminders", label: "Task reminders", description: "When a task is due within 24 hours, and when it becomes overdue." },
  { key: "task_completed", label: "Task completed", description: "A quiet confirmation when you finish a task." },
  { key: "note_reminders", label: "Note reminders", description: "When a reminder you set on a note comes due." },
  { key: "sharing", label: "Sharing", description: "When someone shares a note with you." },
  { key: "calendar_sync", label: "Calendar sync", description: "When a task is added to Google Calendar, and if syncing fails." },
  { key: "integrations", label: "Connected tools", description: "Connected, disconnected, or an authorization that needs renewing." },
];

/** Per-kind switches. Saved immediately; the server enforces them when raising notifications. */
export function NotificationSettings() {
  const { data: user, isPending } = useCurrentUser();
  const update = useUpdateProfile();
  if (isPending || !user) return <Skeleton className="h-64 w-full rounded-2xl" />;
  const prefs = user.notifications ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>In-app notifications</CardTitle>
        <CardDescription>Choose what shows up under the bell. Nothing here sends email.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-glass-border">
          {GROUPS.map((g) => {
            const on = prefs[g.key] !== false;
            const id = `notif-${g.key}`;
            return (
              <li key={g.key} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <Label htmlFor={id} className="text-sm font-medium">
                    {g.label}
                  </Label>
                  <p className="text-xs text-muted-foreground">{g.description}</p>
                </div>
                <Switch
                  id={id}
                  checked={on}
                  disabled={update.isPending}
                  onCheckedChange={(checked) =>
                    update.mutate(
                      { notifications: { [g.key]: checked } },
                      { onError: (e) => toast.error(messageFor(e)) },
                    )
                  }
                />
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
