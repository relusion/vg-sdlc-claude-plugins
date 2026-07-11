import { describe, expect, it } from "vitest";
import { requireProjectRole } from "../src/auth/permissions";

describe("project deletion RBAC", () => {
  it("rejects editors before destructive project actions", () => {
    expect(() => requireProjectRole("editor", "owner")).toThrow("forbidden");
  });
});
