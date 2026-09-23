import { PageHeader } from "@/components/layout/page-header";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { settingsNav } from "@/lib/navigation";
import Link from "next/link";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Manage your account, security and AI preferences." />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[210px_minmax(0,1fr)]">
        <nav aria-label="Settings" className="glass rounded-2xl p-2 md:sticky md:top-2 md:self-start">
          <div className="grid gap-1 md:hidden">
            {settingsNav.map((item) => { const Icon = item.icon; return <Link key={item.href} href={item.href} className="flex min-h-12 items-center gap-3 rounded-xl px-3 text-sm font-medium hover:bg-accent"><Icon className="size-4 text-ai" />{item.label}</Link>; })}
          </div>
          <SidebarNav nav="settings" orientation="vertical" className="hidden md:flex" />
        </nav>
        <div className="min-w-0 max-w-2xl has-[[data-wide]]:max-w-none">{children}</div>
      </div>
    </div>
  );
}
