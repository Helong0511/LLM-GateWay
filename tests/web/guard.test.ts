import { describe, expect, it } from "vitest";

import { isStaffRoles, loginRedirect, postLoginPath, safeNext } from "@/lib/guard";

describe("guard login routing", () => {
  it("uses one login entry for all guarded pages", () => {
    expect(loginRedirect("/admin/users", false)).toBe("/login?next=%2Fadmin%2Fusers");
    expect(loginRedirect("/console", false)).toBe("/login?next=%2Fconsole");
    expect(loginRedirect("/login", false)).toBeNull();
  });

  it("routes by role after login and allows admin next for staff", () => {
    expect(postLoginPath(null, ["admin", "user"])).toBe("/admin");
    expect(postLoginPath(null, ["user"])).toBe("/console");
    expect(postLoginPath("/console/billing", ["admin", "user"])).toBe("/console/billing");
    expect(postLoginPath("/admin/coupons", ["user"])).toBe("/console");
    expect(safeNext("/admin", "/console")).toBe("/admin");
    expect(isStaffRoles(["finance", "user"])).toBe(true);
    expect(isStaffRoles(["user"])).toBe(false);
  });
});
