import { messages } from "@/content";
import { resolveLocale } from "@/lib/locale-server";
import { cookies } from "next/headers";

import { OverviewRefresh } from "@/components/overview-refresh";

const METRIC_KEYS = [
  ["users", "users"],
  ["active_users", "activeUsers"],
  ["providers", "providers"],
  ["published_models", "publishedModels"],
  ["active_api_keys", "activeKeys"],
  ["payment_orders", "paymentOrders"],
  ["ledger_entries", "ledgerEntries"],
  ["audit_events", "auditEvents"],
] as const;

export async function AdminOverview() {
  const locale = await resolveLocale();
  const page = messages[locale].admin.pages.overview;
  const jar = await cookies();
  const cookie = jar
    .getAll()
    .map((item) => `${item.name}=${item.value}`)
    .join("; ");
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  let status = 0;
  let message = "";
  let metrics: Record<string, number> | null = null;
  try {
    const response = await fetch(`${base}/api/admin/overview`, {
      headers: cookie ? { cookie } : undefined,
      cache: "no-store",
    });
    status = response.status;
    const body = (await response.json()) as {
      data?: Record<string, number>;
      error?: { message?: string };
    };
    if (response.ok && body.data) {
      metrics = body.data;
    } else {
      message = body.error?.message ?? page.unavailable;
    }
  } catch {
    message = page.unreachable;
  }

  return (
    <section>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{page.title}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{page.lead}</p>
        </div>
        <OverviewRefresh />
      </div>
      {metrics ? (
        <dl className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {METRIC_KEYS.map(([key, labelKey]) => (
            <div key={key} className="rounded-lg border border-border bg-card p-4">
              <dt className="text-sm text-foreground/70">{page[labelKey]}</dt>
              <dd className="mt-2 text-3xl font-semibold tracking-tight">{metrics[key] ?? 0}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-8 text-sm leading-6">
          {status === 401 ? page.needLogin : status === 403 ? page.forbidden : message}
        </p>
      )}
    </section>
  );
}
