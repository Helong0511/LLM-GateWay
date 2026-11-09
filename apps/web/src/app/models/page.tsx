"use client";

import Link from "next/link";

import { useI18n } from "@/components/locale-provider";
import { DemoMark, SiteShell } from "@/components/site-shell";

export default function ModelsPage() {
  const { t } = useI18n();
  return (
    <SiteShell>
      <section className="max-w-3xl">
        <h1 className="text-4xl font-semibold tracking-tight">{t.models.title}</h1>
        <p className="mt-4 text-base leading-7 text-foreground/75">{t.models.lead}</p>
      </section>
      <section className="grid gap-3 lg:grid-cols-3">
        {t.home.interfaces.map((row) => (
          <article key={row.path} className="rounded-xl border border-border p-5">
            <h2 className="text-lg font-medium">{row.name}</h2>
            <p className="mt-3 font-mono text-xs text-foreground/70">{row.path}</p>
            <p className="mt-3 text-sm leading-6 text-foreground/75">{row.state}</p>
          </article>
        ))}
      </section>
      <article className="max-w-3xl rounded-xl border border-dashed border-border p-5">
        <DemoMark />
        <h2 className="mt-3 text-lg font-medium">{t.models.emptyTitle}</h2>
        <p className="mt-2 text-sm leading-6 text-foreground/75">{t.models.emptyBody}</p>
        <p className="mt-3 text-sm">
          <Link href="/models/demo-model">{t.models.open}</Link>
        </p>
      </article>
    </SiteShell>
  );
}
