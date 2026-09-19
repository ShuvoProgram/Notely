import type { Metadata } from "next";
import { Suspense } from "react";

import { SearchPage } from "@/features/search/components/search-page";

export const metadata: Metadata = { title: "Search" };

export default function SearchRoute() {
  return (
    <Suspense>
      <SearchPage />
    </Suspense>
  );
}
