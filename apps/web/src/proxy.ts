import { NextResponse, type NextRequest } from "next/server";

/** 由后端决定的角色集合，admin 路径需要其一。 */
const STAFF_ROLES = new Set(["support", "finance", "operator", "model_ops", "admin", "superadmin"]);

function isStaffRoles(roles: unknown): boolean {
  if (!Array.isArray(roles)) return false;
  return roles.some((role) => typeof role === "string" && STAFF_ROLES.has(role));
}

/**
 * 服务端鉴权代理：
 *   - /admin/** 和 /console/** 先到这里，用 cookie 向 /api/auth/me 验会话，
 *     通过才发 HTML，否则直接 302 到登录页，避免客户端闪屏。
 *   - /api/** / _next/** / 静态资源不拦截，也不在 matcher 里。
 */
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isAdmin = pathname === "/admin" || pathname.startsWith("/admin/");
  const isConsole = pathname === "/console" || pathname.startsWith("/console/");
  if (!isAdmin && !isConsole) {
    return NextResponse.next();
  }

  // 透传 cookie + x-request-id 给后端验会话
  const requestHeaders = new Headers();
  const cookies = request.cookies.getAll();
  for (const { name, value } of cookies) {
    requestHeaders.set("cookie", `${name}=${value}`);
  }
  const rid = request.headers.get("x-request-id");
  if (rid) requestHeaders.set("x-request-id", rid);

  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  let meResponse: Response;
  try {
    meResponse = await fetch(`${base}/api/auth/me`, {
      method: "GET",
      headers: requestHeaders,
      cache: "no-store",
    });
  } catch {
    // 后端挂了也别放进来，503 更清晰
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname);
    const res = NextResponse.redirect(url);
    res.headers.set("X-Proxy-Reason", "upstream-unavailable");
    return res;
  }

  if (!meResponse.ok) {
    // 401 / 403：清掉浏览器端可能残留的 session cookie，再跳登录
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname);
    const res = NextResponse.redirect(url);
    res.cookies.delete("session");
    // production 用的 cookie 名可能不同，顺手清一下
    res.cookies.delete("__Host-session");
    res.headers.set("X-Proxy-Reason", "unauthenticated");
    return res;
  }

  let data: { roles?: unknown } = {};
  try {
    const json = (await meResponse.json()) as { data?: unknown };
    if (json.data && typeof json.data === "object") data = json.data as typeof data;
  } catch {
    // 后端返回坏 JSON，谨慎起见也放登录
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  // admin 路径额外校验 staff 角色
  if (isAdmin && !isStaffRoles(data.roles)) {
    const url = new URL("/console", request.url);
    const res = NextResponse.redirect(url);
    res.headers.set("X-Proxy-Reason", "forbidden-admin");
    return res;
  }

  // 后端可能 Set-Cookie（滑动续期时），透传回浏览器
  const response = NextResponse.next();
  const upstreamSetCookie = meResponse.headers.getSetCookie();
  for (const cookie of upstreamSetCookie) {
    response.headers.append("set-cookie", cookie);
  }
  response.headers.set("X-Proxy-Auth", "ok");
  return response;
}

export const config = {
  matcher: ["/admin/:path*", "/console/:path*"],
};
