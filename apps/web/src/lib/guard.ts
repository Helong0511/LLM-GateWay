const GUARDED = ["/console", "/admin"];

export const STAFF_ROLES = new Set([
  "support",
  "finance",
  "operator",
  "model_ops",
  "admin",
  "superadmin",
]);

export function isGuardedPath(pathname: string): boolean {
  return GUARDED.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function loginRedirect(pathname: string, hasSession: boolean): string | null {
  if (!isGuardedPath(pathname) || hasSession) {
    return null;
  }
  return `/login?next=${encodeURIComponent(pathname)}`;
}

export function safeNext(value: string | null, fallback = "/console"): string {
  if (value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/login")) {
    return value;
  }
  return fallback;
}

export function isStaffRoles(roles: unknown): boolean {
  if (!Array.isArray(roles)) {
    return false;
  }
  return roles.some((role) => typeof role === "string" && STAFF_ROLES.has(role));
}

/** 统一登录后按角色落地：有运营角色进后台，否则进客户控制台。 */
export function postLoginPath(next: string | null, roles: unknown): string {
  const staff = isStaffRoles(roles);
  const requested = safeNext(next, "");
  if (requested) {
    if (requested === "/admin" || requested.startsWith("/admin/")) {
      return staff ? requested : "/console";
    }
    return requested;
  }
  return staff ? "/admin" : "/console";
}
