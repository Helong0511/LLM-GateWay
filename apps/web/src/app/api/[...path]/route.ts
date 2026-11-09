import { NextRequest, NextResponse } from "next/server";

import { buildUpstreamUrl, upstreamSegments } from "@/lib/bff";

const FORWARDED_REQUEST_HEADERS = [
  "cookie",
  "content-type",
  "x-request-id",
  "idempotency-key",
  "authorization",
  "origin",
  // 真实客户端 IP：nginx 写入后必须原样带到 API，否则限流 / Key IP 白名单 /
  // USDT 回调白名单全部退化成「全站同一个 IP」。
  "x-forwarded-for",
  "x-real-ip",
  "x-forwarded-proto",
];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "x-request-id", "cache-control"];
const MAX_BODY_BYTES = Number(process.env.BFF_MAX_BODY_BYTES ?? 4 * 1024 * 1024);

function tooLarge(contentLength: string | null): boolean {
  if (!contentLength) return false;
  const size = Number(contentLength);
  return Number.isFinite(size) && size > MAX_BODY_BYTES;
}

function payloadTooLarge() {
  return NextResponse.json(
    {
      ok: false,
      data: null,
      error: { code: "PAYLOAD_TOO_LARGE", message: "Request body too large", details: {} },
      request_id: "bff",
    },
    { status: 413 },
  );
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  let target: string;
  try {
    target = buildUpstreamUrl(base, upstreamSegments(path), request.nextUrl.search);
  } catch {
    return NextResponse.json(
      {
        ok: false,
        data: null,
        error: { code: "VALIDATION_ERROR", message: "Invalid path", details: {} },
        request_id: "bff",
      },
      { status: 400 },
    );
  }

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) {
      headers.set(name, value);
    }
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  if (hasBody && tooLarge(request.headers.get("content-length"))) {
    return payloadTooLarge();
  }
  let body: ArrayBuffer | undefined;
  if (hasBody) {
    body = await request.arrayBuffer();
    // 分块传输没有 content-length，只能在读完后按实际字节数兜底拦截。
    if (body.byteLength > MAX_BODY_BYTES) {
      return payloadTooLarge();
    }
  }
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        data: null,
        error: { code: "DEPENDENCY_UNAVAILABLE", message: "Upstream API unreachable", details: {} },
        request_id: "bff",
      },
      { status: 503 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) {
      responseHeaders.set(name, value);
    }
  }
  const setCookies = typeof upstream.headers.getSetCookie === "function" ? upstream.headers.getSetCookie() : [];
  for (const cookie of setCookies) {
    responseHeaders.append("set-cookie", cookie);
  }

  return new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
