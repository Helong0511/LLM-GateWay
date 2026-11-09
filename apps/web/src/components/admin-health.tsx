"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  loadFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { errorMessage, getJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { RefreshButton } from "@/components/ui/refresh-button";

type Health = { status: string; postgres: string; redis: string; appEnv: string; mode: string; mockPayments: boolean };

async function pullHealth(loadFail: string): Promise<{ health: Health | null; message: string }> {
  const result = await getJson("/api/admin/health");
  if (!result.ok || !result.envelope.data) {
    return { health: null, message: errorMessage(result.envelope, loadFail) };
  }
  const data = result.envelope.data;
  const checks = data.checks;
  const postgres = checks && typeof checks === "object" && typeof (checks as Record<string, unknown>).postgres === "string" ? (checks as Record<string, unknown>).postgres : "";
  const redis = checks && typeof checks === "object" && typeof (checks as Record<string, unknown>).redis === "string" ? (checks as Record<string, unknown>).redis : "";
  return {
    health: {
      status: typeof data.status === "string" ? data.status : "",
      postgres: String(postgres),
      redis: String(redis),
      appEnv: typeof data.app_env === "string" ? data.app_env : "",
      mode: typeof data.operating_mode === "string" ? data.operating_mode : "",
      mockPayments: data.mock_payments_enabled === true,
    },
    message: "",
  };
}

export function AdminHealth() {
  const { t } = useI18n();
  const [health, setHealth] = useState<Health | null>(null);
  const { flash, setFlash } = useBootFlash(t.admin.pages.health.loading);

  useEffect(() => {
    void (async () => {
      const next = await pullHealth(t.admin.pages.health.loadFail);
      setHealth(next.health);
      setFlash(loadFlash(next.message));
    })();
  }, []);

  async function load() {
    const next = await pullHealth(t.admin.pages.health.loadFail);
    setHealth(next.health);
    setFlash(loadFlash(next.message));
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.health.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.health.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      {health ? (
        <dl className="grid max-w-md gap-2 text-sm">
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.health.status}</dt>
            <dd>{health.status === "ready" ? t.admin.pages.health.ready : t.admin.pages.health.notReady}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.health.postgres}</dt>
            <dd>{health.postgres}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.health.redis}</dt>
            <dd>{health.redis}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.health.env}</dt>
            <dd>{health.appEnv}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.health.mode}</dt>
            <dd>{health.mode}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.health.mockPayments}</dt>
            <dd>{health.mockPayments ? t.admin.pages.health.on : t.admin.pages.health.off}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
