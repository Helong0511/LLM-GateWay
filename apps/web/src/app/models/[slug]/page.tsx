"use client";

import { notFound, useParams } from "next/navigation";

import { useI18n } from "@/components/locale-provider";
import { DemoMark, SiteShell } from "@/components/site-shell";

export default function ModelDetailPage() {
  const params = useParams<{ slug: string }>();
  const { t } = useI18n();
  if (params.slug !== "demo-model") {
    notFound();
  }
  return (
    <SiteShell>
      <article className="max-w-3xl">
        <DemoMark />
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">{t.models.detailTitle}</h1>
        <p className="mt-4 text-sm leading-6 text-foreground/80">{t.models.detailBody}</p>
      </article>
    </SiteShell>
  );
}
