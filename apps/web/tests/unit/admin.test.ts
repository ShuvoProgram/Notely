import { describe, expect, it } from "vitest";

import { toQuery } from "@/features/admin/api";
import { safeNext } from "@/features/auth/hooks";
import { isActive, adminNav } from "@/lib/navigation";

describe("admin query strings", () => {
  it("drops empty filters and encodes values", () => {
    expect(toQuery({ q: "a b&c", status: "", role: null, page: 2, flag: undefined })).toBe("?q=a+b%26c&page=2");
    expect(toQuery({ q: "" })).toBe("");
  });
});

describe("post-sign-in redirects", () => {
  it("allows the admin console but never another origin", () => {
    expect(safeNext("/admin")).toBe("/admin");
    expect(safeNext("/admin/users?q=x")).toBe("/admin/users?q=x");
    expect(safeNext("//evil.example/admin")).toBe("/app");
    expect(safeNext("https://evil.example")).toBe("/app");
    expect(safeNext("/administrator")).toBe("/app");
  });
});

describe("admin navigation", () => {
  it("marks only the most specific item active", () => {
    const users = adminNav.find((i) => i.href === "/admin/users")!;
    const overview = adminNav.find((i) => i.href === "/admin")!;
    expect(isActive("/admin/users/123", users, adminNav)).toBe(true);
    expect(isActive("/admin/users/123", overview, adminNav)).toBe(false);
    expect(isActive("/admin", overview, adminNav)).toBe(true);
  });
});
