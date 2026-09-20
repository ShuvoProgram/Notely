import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">That page doesn&apos;t exist or was moved.</p>
      <Button asChild>
        <Link href="/app">Back to Notely</Link>
      </Button>
    </main>
  );
}
