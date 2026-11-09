"use client";

import { SiteShell } from "@/components/site-shell";
import { StatusPanel } from "@/components/status-panel";
import { useI18n } from "@/components/locale-provider";

export default function StatusPage() {
  const { t } = useI18n();
  return (
    <SiteShell>
      <section className="max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight">{t.status.pageTitle}</h1>
        <p className="mt-3 text-sm text-foreground/70">{t.status.pageLead}</p>
      </section>
      <StatusPanel />
    </SiteShell>
  );
}
