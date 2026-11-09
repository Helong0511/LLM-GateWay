import { NextRequest, NextResponse } from "next/server";

import { buildUpstreamUrl, upstreamSegments } from "@/lib/bff";

const FORWARDED_REQUEST_HEADERS = [
  "cookie",
  "content-type",
  "x-request-id",
  "idempotency-key",
  "authorization",
  "origin",
];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "x-request-id", "cache-control"];

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
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
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
