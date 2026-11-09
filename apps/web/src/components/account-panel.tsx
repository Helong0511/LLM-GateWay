"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
    type FlashMessage,
} from "@/components/ui/flash";

import { ConsoleNav } from "@/components/console-nav";
import { TrendChart } from "@/components/trend-chart";
import { getJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { displayMoney } from "@/lib/money";
import { statusLabel } from "@/lib/status-label";

type Account = {
  email: string;
  status: string;
  roles: string[];
};

type Summary = {
  balance: string | null;
  currency: string;
  todayCharge: string | null;
  todayRequests: number | null;
  todayTokens: number | null;
  successRate: string | null;
  avgLatencyMs: number | null;
  monthRequests: number | null;
  trend: { day: string; requests: number; tokens: number }[];
};

export function AccountPanel() {
  const { t } = useI18n();
  const a = t.console.account;
  const [account, setAccount] = useState<Account | null>(null);
  const { flash, setFlash } = useBootFlash(t.console.account.loading);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    void (async () => {
      const result = await getJson("/api/auth/me");
      if (!result.ok || !result.envelope.data) {
        setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.account.sessionExpired)));
        return;
      }
      const user = result.envelope.data.user;
      const roles = result.envelope.data.roles;
      if (!isRecord(user) || typeof user.email !== "string" || !Array.isArray(roles)) {
        setFlash(errFlash(t.console.account.loadFail));
        return;
      }
      setAccount({
        email: user.email,
        status: typeof user.status === "string" ? user.status : "",
        roles: roles.filter((item): item is string => typeof item === "string"),
      });
      setFlash(null);
      const summaryResult = await getJson("/api/console/summary");
      const data = summaryResult.envelope.data;
      if (summaryResult.ok && data) {
        setSummary({
          balance: typeof data.balance === "string" ? data.balance : null,
          currency: typeof data.currency === "string" ? data.currency : "USD",
          todayCharge: typeof data.today_charge === "string" ? data.today_charge : null,
          todayRequests: typeof data.today_requests === "number" ? data.today_requests : null,
          todayTokens: typeof data.today_tokens === "number" ? data.today_tokens : null,
          successRate: typeof data.success_rate === "string" ? data.success_rate : null,
          avgLatencyMs: typeof data.avg_latency_ms === "number" ? data.avg_latency_ms : null,
          monthRequests: typeof data.month_requests === "number" ? data.month_requests : null,
          trend: Array.isArray(data.trend)
            ? data.trend.flatMap((item) => {
                if (!item || typeof item !== "object") {
                  return [];
                }
                const row = item as Record<string, unknown>;
                if (typeof row.day !== "string" || typeof row.requests !== "number" || typeof row.tokens !== "number") {
                  return [];
                }
                return [{ day: row.day, requests: row.requests, tokens: row.tokens }];
              })
            : [],
        });
      }
    })();
  }, []);

  const roleText = account?.roles.includes("user")
    ? ""
    : ` · ${account?.roles.map((role) => statusLabel(t, "role", role)).join("、") || a.noRole}`;

  return (
    <section className="max-w-4xl space-y-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{a.title}</h1>
        <p className="mt-2 text-sm text-foreground/70">
          {account ? a.welcomeBack.replace("{email}", account.email) : a.lead}
        </p>
      </header>
      <ConsoleNav />
      {flash ? <FlashBanner flash={flash} compact className="mt-0" /> : null}
      {summary ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="tech-panel rounded-lg px-4 py-4 sm:col-span-2">
            <p className="text-xs text-foreground/55">{a.availableBalance}</p>
            <p className="mt-2 text-2xl font-semibold tracking-tight">
              {displayMoney(summary.balance, summary.currency)}
            </p>
            <p className="mt-3 text-xs text-foreground/50">
              {a.status} {statusLabel(t, "user", account?.status)}
              {roleText}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card/70 px-4 py-4">
            <p className="text-xs text-foreground/55">{a.todaySpend}</p>
            <p className="mt-2 text-xl font-semibold">
              {summary.todayCharge ? displayMoney(summary.todayCharge, summary.currency) : a.none}
            </p>
            <p className="mt-2 text-xs text-foreground/50">
              {a.requests} {summary.todayRequests ?? 0} · token {summary.todayTokens ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card/70 px-4 py-4">
            <p className="text-xs text-foreground/55">{a.todaySuccessRate}</p>
            <p className="mt-2 text-xl font-semibold">{summary.successRate ?? a.noCalls}</p>
            <p className="mt-2 text-xs text-foreground/50">
              {summary.avgLatencyMs === null
                ? a.noLatency
                : a.avgMs.replace("{ms}", String(summary.avgLatencyMs))}{" "}
              · {a.monthRequests} {summary.monthRequests ?? 0}
            </p>
          </div>
        </div>
      ) : null}
      <ul className="grid gap-3 text-sm sm:grid-cols-3">
        <li className="rounded-lg border border-border bg-card/70 px-4 py-3 transition-colors hover:border-accent/40">
          <Link href="/console/api-keys" className="font-medium">
            {a.createKey}
          </Link>
          <p className="mt-1 text-foreground/60">{a.createKeyHint}</p>
        </li>
        <li className="rounded-lg border border-border bg-card/70 px-4 py-3 transition-colors hover:border-accent/40">
          <Link href="/console/billing" className="font-medium">
            {a.topUp}
          </Link>
          <p className="mt-1 text-foreground/60">{a.topUpHint}</p>
        </li>
        <li className="rounded-lg border border-border bg-card/70 px-4 py-3 transition-colors hover:border-accent/40">
          <Link href="/quickstart" className="font-medium">
            {a.quickstart}
          </Link>
          <p className="mt-1 text-foreground/60">{a.quickstartHint}</p>
        </li>
      </ul>
      {summary ? <TrendChart points={summary.trend} /> : null}
      <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
        <Link href="/console/models" className="text-accent hover:underline">
          {a.browseModels}
        </Link>
        <Link href="/console/usage" className="text-accent hover:underline">
          {a.viewUsage}
        </Link>
        <Link href="/console/security" className="text-foreground/70 hover:text-foreground">
          {a.passwordSecurity}
        </Link>
        <Link href="/console/profile" className="text-foreground/70 hover:text-foreground">
          {a.profile}
        </Link>
      </div>
      <p className="text-xs text-foreground/55">{a.statsNote}</p>
    </section>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
