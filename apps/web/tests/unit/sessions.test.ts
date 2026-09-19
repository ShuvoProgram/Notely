import { describeAgent } from "@/features/settings/components/sessions-list";
import { initialsOf } from "@/components/layout/user-menu";

describe("describeAgent", () => {
  it("recognises common desktop browsers", () => {
    expect(
      describeAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"),
    ).toEqual({ label: "Chrome on Windows", mobile: false });
  });
  it("flags mobile agents", () => {
    expect(describeAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148 Safari/604.1").mobile).toBe(true);
  });
  it("handles missing agents", () => {
    expect(describeAgent(null).label).toBe("Unknown device");
  });
});

describe("initialsOf", () => {
  it("takes up to two initials", () => {
    expect(initialsOf("Ada Lovelace")).toBe("AL");
    expect(initialsOf("ada")).toBe("A");
    expect(initialsOf("")).toBe("");
  });
});
