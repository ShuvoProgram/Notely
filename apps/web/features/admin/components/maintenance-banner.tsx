"use client";

import { useQuery } from "@tanstack/react-query";

import { AlertTriangle } from "@/components/icons";
import { api } from "@/lib/api/client";

interface SystemStatus {
  maintenance: { enabled: boolean; message: string | null };
  signups_enabled: boolean;
  ai_enabled: boolean;
  automations_enabled: boolean;
}

/** Shown across the workspace while an admin has maintenance mode on (saving is paused). */
export function MaintenanceBanner() {
  const status = useQuery({
    queryKey: ["system", "status"],
    queryFn: () => api.get<SystemStatus>("/system/status"),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });
  if (!status.data?.maintenance.enabled) return null;
  return (
    <div role="status" className="z-10 flex shrink-0 items-center gap-2 border-b border-warning/40 bg-warning/15 px-4 py-2 text-sm">
      <AlertTriangle className="size-4 shrink-0 text-warning" aria-hidden />
      <span className="min-w-0">{status.data.maintenance.message ?? "Notely is under maintenance. Changes are paused."}</span>
    </div>
  );
}
