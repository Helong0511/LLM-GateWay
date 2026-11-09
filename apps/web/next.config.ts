import type { NextConfig } from "next";

/**
 * 浏览器侧安全响应头。
 *
 * API 侧（FastAPI 中间件）已经带了 nosniff / X-Frame-Options，但真正给用户
 * 返回 HTML 的是 Next，页面响应此前完全没有 CSP / HSTS。这里统一补齐，
 * 让后台页面即使出现一处 XSS，也不至于被直接拿去外连或内嵌钓鱼。
 *
 * CSP 说明：Next 的 hydration 依赖内联脚本，未接入 nonce 之前 script-src
 * 必须保留 'unsafe-inline'。等接入 nonce 后应收紧为 'strict-dynamic'。
 */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
];

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  reactStrictMode: true,
  poweredByHeader: false,
  allowedDevOrigins: ["127.0.0.1"],
  agentRules: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
