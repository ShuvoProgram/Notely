import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { LEGAL } from "@/lib/legal";

const LINKS = [
  { href: "/privacy-policy", label: "Privacy Policy" },
  { href: "/terms-and-conditions", label: "Terms & Conditions" },
  { href: `mailto:${LEGAL.contactEmail}`, label: "Contact" },
];

/** Public-site footer with the legal links. Rendered on the landing and legal pages. */
export function SiteFooter() {
  return (
    <footer className="mt-auto border-t">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-3">
          <Logo compact />
          <span>© {new Date().getFullYear()} {LEGAL.companyName}. All rights reserved.</span>
        </div>
        <nav aria-label="Legal" className="flex flex-wrap gap-x-5 gap-y-2">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="underline-offset-4 hover:text-foreground hover:underline">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
