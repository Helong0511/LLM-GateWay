"use client";

import { notFound } from "next/navigation";

import { useI18n } from "@/components/locale-provider";
import { SiteShell } from "@/components/site-shell";
import type { ArticleSlug } from "@/content/messages";

const SLUGS = new Set<string>([
  "features",
  "solutions",
  "pricing",
  "docs",
  "quickstart",
  "faq",
  "contact",
  "terms",
  "privacy",
]);

export function ArticlePage({ slug }: { slug: string }) {
  const { t } = useI18n();
  if (!SLUGS.has(slug)) {
    notFound();
  }
  const article = t.articles[slug as ArticleSlug];
  return (
    <SiteShell>
      <article className="max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight">{article.title}</h1>
        <div className="mt-6 space-y-4 text-sm leading-6 text-foreground/80">
          {article.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
      </article>
    </SiteShell>
  );
}
