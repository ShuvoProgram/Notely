import Link from "next/link";

import { SearchIcon } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";

export default function AdminNotFound() {
  return (
    <div className="glass mx-auto mt-6 max-w-lg rounded-2xl">
      <EmptyState
        icon={SearchIcon}
        title="Not found"
        description="That record doesn't exist or was removed."
        action={
          <Button asChild variant="outline">
            <Link href="/admin">Back to overview</Link>
          </Button>
        }
      />
    </div>
  );
}
