import { SidebarNav } from "@/components/layout/sidebar-nav";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Manage your account and workspace.</p>
      </div>
      <div className="grid gap-8 md:grid-cols-[200px_1fr]">
        <nav aria-label="Settings">
          <SidebarNav nav="settings" orientation="vertical" className="md:flex-col flex-row overflow-x-auto" />
        </nav>
        <div className="min-w-0 max-w-2xl">{children}</div>
      </div>
    </div>
  );
}
