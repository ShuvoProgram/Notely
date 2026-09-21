import { PageHeader } from "@/components/layout/page-header";
import { SidebarNav } from "@/components/layout/sidebar-nav";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Manage your account, security and AI preferences." />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[210px_minmax(0,1fr)]">
        <nav aria-label="Settings" className="glass rounded-2xl p-2 md:sticky md:top-2 md:self-start">
          <SidebarNav nav="settings" orientation="vertical" className="flex-row overflow-x-auto md:flex-col" />
        </nav>
        <div className="min-w-0 max-w-2xl has-[[data-wide]]:max-w-none">{children}</div>
      </div>
    </div>
  );
}
