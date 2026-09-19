import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// next/navigation is not available outside the Next runtime.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/app",
  redirect: vi.fn(),
}));
