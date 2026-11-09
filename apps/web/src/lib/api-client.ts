export type Envelope = {
  ok?: boolean;
  data?: Record<string, unknown> | null;
  error?: { code?: string; message?: string; details?: Record<string, unknown> } | null;
};

export async function postJson(
  path: string,
  body: unknown,
  headers?: Record<string, string>,
): Promise<{ ok: boolean; status: number; envelope: Envelope }> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (path === "/api/auth/login" || path === "/api/auth/logout" || path === "/api/auth/register") {
    clearSessionCache();
  }
  return { ok: response.ok, status: response.status, envelope: await envelopeOf(response) };
}

export async function patchJson(path: string, body: unknown): Promise<{ ok: boolean; status: number; envelope: Envelope }> {
  const response = await fetch(path, {
    method: "PATCH",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { ok: response.ok, status: response.status, envelope: await envelopeOf(response) };
}

export async function deleteJson(path: string): Promise<{ ok: boolean; status: number; envelope: Envelope }> {
  const response = await fetch(path, { method: "DELETE", credentials: "include" });
  return { ok: response.ok, status: response.status, envelope: await envelopeOf(response) };
}

export async function getJson(path: string): Promise<{ ok: boolean; status: number; envelope: Envelope }> {
  const response = await fetch(path, { credentials: "include", cache: "no-store" });
  return { ok: response.ok, status: response.status, envelope: await envelopeOf(response) };
}

async function envelopeOf(response: Response): Promise<Envelope> {
  try {
    return (await response.json()) as Envelope;
  } catch {
    return {
      ok: false,
      error: {
        code: "BAD_RESPONSE",
        message: "",
        details: { status: response.status },
      },
    };
  }
}

/* ------------------------------------------------------------------ */
/* 会话探测缓存：同一浏览器标签内多组件共享一次 /api/auth/me 请求。      */
/* 未登录时探测返回 401 属预期语义，缓存命中可避免每次导航重复请求，     */
/* 从源头消除后端访问日志中的 401 噪音。登录/登出/注册后自动失效。       */
/* ------------------------------------------------------------------ */

const SESSION_TTL_MS = 30_000;

let sessionCache: { value: { ok: boolean; status: number; envelope: Envelope }; at: number } | null = null;
let sessionInFlight: Promise<{ ok: boolean; status: number; envelope: Envelope }> | null = null;

/** 带 30 秒 TTL 与并发去重的会话探测；并发调用共享同一请求。 */
export function getMeCached(): Promise<{ ok: boolean; status: number; envelope: Envelope }> {
  if (sessionCache && Date.now() - sessionCache.at < SESSION_TTL_MS) {
    return Promise.resolve(sessionCache.value);
  }
  if (sessionInFlight) {
    return sessionInFlight;
  }
  sessionInFlight = getJson("/api/auth/me").then((value) => {
    sessionCache = { value, at: Date.now() };
    return value;
  });
  void sessionInFlight.finally(() => {
    sessionInFlight = null;
  });
  return sessionInFlight;
}

/** 立即失效会话缓存（登录/登出/注册后调用）。 */
export function clearSessionCache(): void {
  sessionCache = null;
}

/** Soft / dependency codes: avoid showing raw status text when a caller fallback exists. */
const SOFT_SYSTEM_CODES = new Set([
  "INTERNAL",
  "DEPENDENCY_UNAVAILABLE",
  "UPSTREAM_ERROR",
  "BAD_RESPONSE",
]);

/**
 * Legacy helper without locale catalog. Prefer `apiErrorLabel(t, …)` in UI.
 * Never surfaces API `message` (server default is zh-CN).
 */
export function errorMessage(envelope: Envelope, fallback: string): string {
  const code = (envelope.error?.code || "").trim();
  if (SOFT_SYSTEM_CODES.has(code)) {
    return fallback;
  }
  return fallback || code;
}
