import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";

export interface SiteSection {
  href: string;
  label: string;
}

/**
 * Public-site header (landing + legal pages). The app shell has its own navigation. Pass
 * `sections` for in-page anchors (the landing page); they collapse away on small screens where the
 * page is a single readable column anyway.
 */
export function SiteHeader({ sections }: { sections?: SiteSection[] }) {
  return (
    <header className="sticky top-0 z-40 border-b border-foreground/10 bg-background/90 backdrop-blur-md supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-6 px-4 py-3.5 sm:px-6">
        <Link href="/" className="rounded-md focus-visible:outline-2" aria-label="Notely home">
          <Logo />
        </Link>
        {sections?.length ? (
          <nav aria-label="On this page" className="hidden items-center gap-7 md:flex">
            {sections.map((s) => (
              <a key={s.href} href={s.href} className="text-sm font-medium text-foreground-secondary underline-offset-8 transition-colors hover:text-foreground hover:underline">
                {s.label}
              </a>
            ))}
          </nav>
        ) : null}
        <nav className="flex items-center gap-1.5 sm:gap-2" aria-label="Account">
          <ThemeToggle />
          <Button variant="ghost" asChild className="rounded-lg">
            <Link href="/login">Sign in</Link>
          </Button>
          <Button variant="outline" asChild className="rounded-lg border-foreground/20 font-bold">
            <Link href="/signup">Sign up</Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}
