"use client";

import Link from "next/link";

import { useI18n } from "@/components/locale-provider";
import { SiteShell } from "@/components/site-shell";

export default function PricingPage() {
  const { t } = useI18n();
  const copy = t.home;
  return (
    <SiteShell>
      <section className="max-w-3xl">
        <h1 className="text-4xl font-semibold tracking-tight">{t.articles.pricing.title}</h1>
        <p className="mt-4 text-base leading-7 text-foreground/75">{copy.billingLead}</p>
      </section>
      <section className="grid gap-3 md:grid-cols-3">
        {copy.packages.map((item, index) => (
          <article key={item.amount} className={index === 1 ? "rounded-xl border-2 border-foreground p-5" : "rounded-xl border border-border p-5"}>
            <p className="text-3xl font-semibold tracking-tight">{item.amount}</p>
            <h2 className="mt-2 text-base font-medium">{item.name}</h2>
            <p className="mt-2 text-sm leading-6 text-foreground/70">{item.body}</p>
          </article>
        ))}
      </section>
      <div className="max-w-3xl space-y-4 text-sm leading-6 text-foreground/75">
        {t.articles.pricing.paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
        <p className="text-xs text-foreground/55">{copy.packageNote}</p>
        <p>
          <Link href="/console/billing">{copy.billingLink}</Link>
        </p>
      </div>
    </SiteShell>
  );
}
