import type { Envelope } from "@/lib/api-client";
import type { Messages } from "@/content/messages";

/** Soft / dependency codes: prefer localized catalog or caller fallback over raw API text. */
const SOFT_SYSTEM_CODES = new Set([
  "INTERNAL",
  "DEPENDENCY_UNAVAILABLE",
  "UPSTREAM_ERROR",
  "BAD_RESPONSE",
]);

/** Coupon redeem failures that are expected user mistakes → warning tone. */
export const COUPON_WARN_CODES = new Set([
  "COUPON_EMPTY",
  "COUPON_BAD_FORMAT",
  "COUPON_NOT_FOUND",
  "COUPON_DELETED",
  "COUPON_DISABLED",
  "COUPON_CURRENCY",
  "COUPON_EXPIRED",
  "COUPON_ALREADY_REDEEMED",
  "COUPON_EXHAUSTED",
]);

function fillTemplate(template: string, details: Record<string, unknown> | undefined): string {
  if (!details) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_full, key: string) => {
    const value = details[key];
    return typeof value === "string" || typeof value === "number" ? String(value) : `{${key}}`;
  });
}

/**
 * Resolve API error text for the active locale.
 * Prefer stable error.code → t.errors, then caller fallback.
 * Never use API `message`: server defaults are zh-CN and break EN/zh-TW UI.
 */
export function apiErrorLabel(t: Messages, envelope: Envelope, fallback: string): string {
  const code = (envelope.error?.code || "").trim();
  const catalog = t.errors as Record<string, string>;
  const details = envelope.error?.details;
  if (code && catalog[code]) {
    return fillTemplate(catalog[code], details);
  }
  if (SOFT_SYSTEM_CODES.has(code) && catalog[code]) {
    return catalog[code];
  }
  return fallback || catalog.INTERNAL || code || "";
}
