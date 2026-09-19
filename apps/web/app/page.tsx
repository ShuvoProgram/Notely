import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { getCurrentUser } from "@/lib/api/server";

export default async function LandingPage() {
  const user = await getCurrentUser();
  if (user) redirect("/app");

  return (
    <div className="flex flex-1 flex-col">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-2">
          <Button variant="ghost" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild>
            <Link href="/signup">Get started</Link>
          </Button>
        </nav>
      </header>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col justify-center px-4 py-16 sm:px-6">
        <p className="mb-4 text-sm font-medium text-ai">AI-first notes</p>
        <h1 className="max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Capture thoughts. Connect your work. Let AI move things forward.
        </h1>
        <p className="mt-5 max-w-xl text-lg text-muted-foreground">
          A calm note-taking workspace with a powerful AI layer underneath it. Write, ask, and
          review changes before anything leaves Notely.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button size="lg" asChild>
            <Link href="/signup">
              Create your workspace <ArrowRight className="size-4" aria-hidden />
            </Link>
          </Button>
          <Button size="lg" variant="outline" asChild>
            <Link href="/login">I already have an account</Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
