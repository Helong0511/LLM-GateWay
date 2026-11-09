"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import type { components } from "@/lib/api/schema";

type HealthResponse = components["schemas"]["HealthResponse"];
type MetaResponse = components["schemas"]["MetaResponse"];
type LoadState = "loading" | "ok" | "error";

type Probe = {
  state: LoadState;
  status: number | null;
  summary: string;
};

function readSummary(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }
  const body = payload as HealthResponse;
  if (body.ok === true && typeof body.data?.status === "string") {
    return body.data.status;
  }
  if (typeof body.error?.message === "string") {
    return body.error.message;
  }
  return fallback;
}

function readMeta(payload: unknown, mockOn: string, mockOff: string): string | null {
  if (!isRecord(payload)) {
    return null;
  }
  const data = (payload as MetaResponse).data;
  if (!data || typeof data.operating_mode !== "string" || typeof data.app_env !== "string") {
    return null;
  }
  const mockText = data.mock_payments_enabled ? mockOn : mockOff;
  return `${data.app_env} / ${data.operating_mode} / ${mockText}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function StatusPanel() {
  const { t } = useI18n();
  const [health, setHealth] = useState<Probe>({ state: "loading", status: null, summary: "" });
  const [meta, setMeta] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load(path: string): Promise<{ state: LoadState; status: number | null; payload: unknown }> {
      try {
        const response = await fetch(path, { cache: "no-store" });
        const payload: unknown = await response.json();
        return { state: response.ok ? "ok" : "error", status: response.status, payload };
      } catch {
        return { state: "error", status: null, payload: null };
      }
    }

    void (async () => {
      const healthResult = await load("/api/healthz");
      const metaResult = await load("/api/meta");
      if (cancelled) {
        return;
      }
      setHealth({
        state: healthResult.state,
        status: healthResult.status,
        summary: readSummary(healthResult.payload, healthResult.state === "error" ? t.status.unreachable : t.status.unknown),
      });
      setMeta(readMeta(metaResult.payload, t.status.mockOn, t.status.mockOff) ?? t.status.modeUnavailable);
    })();

    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <section className="rounded-lg border border-border bg-card p-5" aria-live="polite">
      <h2 className="text-lg font-medium">{t.status.title}</h2>
      <p className="mt-2 text-sm text-foreground/70">{t.status.lead}</p>
      <dl className="mt-4 space-y-3 text-sm">
        <div className="flex justify-between gap-4">
          <dt>{t.status.health}</dt>
          <dd>
            {health.state === "loading" ? t.status.checking : `${health.summary}${health.status ? `（HTTP ${health.status}）` : ""}`}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>{t.status.mode}</dt>
          <dd>{meta || t.status.checking}</dd>
        </div>
      </dl>
    </section>
  );
}
