"use client";

import Link from "next/link";
import { useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { SiteShell } from "@/components/site-shell";
import { StatusPanel } from "@/components/status-panel";
import { Button } from "@/components/ui/button";
import { estimateUsage, type Level, type Workflow } from "@/lib/estimate";

const SAMPLES = {
  curl: `curl "$ORIGIN/v1/chat/completions" \\
  -H "Authorization: Bearer $FORGE_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "your-model",
    "messages": [{"role": "user", "content": "Hello"}]
  }'`,
  python: `from openai import OpenAI

client = OpenAI(
    base_url="https://your-host/v1",
    api_key="sk-...",
)
reply = client.chat.completions.create(
    model="your-model",
    messages=[{"role": "user", "content": "Hello"}],
)`,
  node: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://your-host/v1",
  apiKey: process.env.FORGE_API_KEY,
});
const reply = await client.chat.completions.create({
  model: "your-model",
  messages: [{ role: "user", content: "Hello" }],
});`,
} as const;

type SampleId = keyof typeof SAMPLES;

function isWorkflow(value: string): value is Workflow {
  return value === "chat" || value === "coding" || value === "agents" || value === "support";
}

function isLevel(value: string): value is Level {
  return value === "light" || value === "regular" || value === "heavy";
}

export function HomePage() {
  const { t } = useI18n();
  const copy = t.home;
  const [sample, setSample] = useState<SampleId>("curl");
  const [workflow, setWorkflow] = useState<Workflow>("chat");
  const [level, setLevel] = useState<Level>("regular");
  const estimate = estimateUsage(workflow, level);

  return (
    <SiteShell>
      <section className="tech-panel relative overflow-hidden rounded-2xl">
        <div
          className="pointer-events-none absolute inset-0 opacity-50 [background-image:linear-gradient(to_right,hsl(var(--border))_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--border))_1px,transparent_1px)] [background-size:28px_28px]"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute -right-16 top-0 h-56 w-56 rounded-full bg-accent/15 blur-3xl"
          aria-hidden
        />
        <div className="relative grid items-start gap-8 px-6 py-10 sm:px-10 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <p className="tech-eyebrow">{copy.eyebrow}</p>
            <h1 className="mt-4 max-w-xl text-4xl font-semibold tracking-tight sm:text-5xl">{copy.title}</h1>
            <p className="mt-4 max-w-xl text-base leading-7 text-foreground/75">{copy.lead}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/register"
                className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground shadow-[0_0_0_1px_hsl(var(--accent)/0.25)]"
              >
                {copy.register}
              </Link>
              <Link href="/docs" className="inline-flex h-10 items-center rounded-md border border-border bg-card/80 px-4 text-sm hover:border-accent/40">
                {copy.docs}
              </Link>
            </div>
          </div>
          <div className="rounded-xl border border-border bg-background/85 p-4 shadow-[inset_0_1px_0_hsl(var(--accent)/0.12)]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-mono text-xs uppercase tracking-[0.14em] text-accent">{copy.sampleTitle}</h2>
              <div className="flex gap-1">
                {(Object.keys(SAMPLES) as SampleId[]).map((id) => (
                  <Button key={id} type="button" size="sm" variant={sample === id ? "default" : "outline"} onClick={() => setSample(id)}>
                    {id === "curl" ? "cURL" : id === "python" ? "Python" : "Node"}
                  </Button>
                ))}
              </div>
            </div>
            <pre className="mt-4 overflow-x-auto rounded-md border border-border/70 bg-muted/80 p-3 text-xs leading-5">{SAMPLES[sample]}</pre>
            <p className="mt-3 text-xs text-foreground/65">{copy.sampleNote}</p>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {copy.metrics.map((item) => (
          <div key={item.label} className="rounded-xl border border-border bg-card/70 px-4 py-4">
            <p className="font-mono text-2xl font-semibold tracking-tight text-accent">{item.value}</p>
            <p className="mt-1 text-sm text-foreground/65">{item.label}</p>
          </div>
        ))}
      </section>

      <section>
        <ol className="grid gap-3 md:grid-cols-3">
          {copy.points.map((point, index) => (
            <li key={point.title} className="rounded-xl border border-border p-5">
              <p className="font-mono text-xs text-foreground/45">{String(index + 1).padStart(2, "0")}</p>
              <h2 className="mt-2 text-base font-medium">{point.title}</h2>
              <p className="mt-2 text-sm leading-6 text-foreground/70">{point.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">{copy.interfacesTitle}</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-foreground/70">{copy.interfacesNote}</p>
          </div>
          <Link href="/models" className="text-sm">
            {t.shell.nav.models}
          </Link>
        </div>
        <div className="mt-5 grid gap-3 lg:grid-cols-3">
          {copy.interfaces.map((row) => (
            <article key={row.path} className="flex flex-col rounded-xl border border-border p-5">
              <h3 className="text-base font-medium">{row.name}</h3>
              <p className="mt-3 font-mono text-xs text-foreground/70">{row.path}</p>
              <p className="mt-3 text-sm leading-6 text-foreground/75">{row.state}</p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">{copy.casesTitle}</h2>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {copy.cases.map((item) => (
            <article key={item.title} className="rounded-xl border border-border bg-muted/40 p-5">
              <h3 className="text-base font-medium">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-foreground/75">{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{copy.billingTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-foreground/70">{copy.billingLead}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {copy.packages.map((item, index) => (
              <article
                key={item.amount}
                className={index === 1 ? "rounded-xl border-2 border-foreground p-4" : "rounded-xl border border-border p-4"}
              >
                <p className="text-3xl font-semibold tracking-tight">{item.amount}</p>
                <h3 className="mt-2 text-sm font-medium">{item.name}</h3>
                <p className="mt-2 text-sm leading-6 text-foreground/70">{item.body}</p>
              </article>
            ))}
          </div>
          <p className="mt-3 text-xs leading-5 text-foreground/55">{copy.packageNote}</p>
          <p className="mt-3 text-sm">
            <Link href="/pricing">{t.shell.nav.pricing}</Link>
            <span className="px-2 text-foreground/30">/</span>
            <Link href="/console/billing">{copy.billingLink}</Link>
          </p>
        </div>
        <div className="rounded-xl border border-border p-5">
          <h2 className="text-lg font-medium">{copy.estimateTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-foreground/70">{copy.estimateLead}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {copy.workflows.map((item) => {
              if (!isWorkflow(item.id)) {
                return null;
              }
              const id = item.id;
              return (
                <Button key={id} type="button" size="sm" variant={workflow === id ? "default" : "outline"} onClick={() => setWorkflow(id)}>
                  {item.label}
                </Button>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {copy.levels.map((item) => {
              if (!isLevel(item.id)) {
                return null;
              }
              const id = item.id;
              return (
                <Button key={id} type="button" size="sm" variant={level === id ? "default" : "outline"} onClick={() => setLevel(id)}>
                  {item.label}
                </Button>
              );
            })}
          </div>
          <dl className="mt-5 grid grid-cols-2 gap-3">
            <div>
              <dt className="text-xs text-foreground/55">{copy.volume}</dt>
              <dd className="mt-1 text-lg font-medium">
                {estimate.millionTokens} {copy.million}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-foreground/55">{copy.suggested}</dt>
              <dd className="mt-1 text-lg font-medium">${estimate.suggestedUsd}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">{copy.productionTitle}</h2>
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {copy.production.map((item) => (
            <article key={item.title} className="rounded-xl border border-border p-5">
              <h3 className="text-base font-medium">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-foreground/70">{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <StatusPanel />

      <section className="grid gap-8 lg:grid-cols-[0.7fr_1.3fr]">
        <h2 className="text-2xl font-semibold tracking-tight">{copy.faqTitle}</h2>
        <div className="space-y-2">
          {copy.faq.map((item) => (
            <details key={item.q} className="rounded-xl border border-border px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium">{item.q}</summary>
              <p className="mt-2 text-sm leading-6 text-foreground/70">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="relative overflow-hidden rounded-2xl border border-accent/25 bg-primary px-6 py-10 text-primary-foreground sm:px-10">
        <div
          className="pointer-events-none absolute inset-0 opacity-25 [background-image:linear-gradient(to_right,currentColor_1px,transparent_1px),linear-gradient(to_bottom,currentColor_1px,transparent_1px)] [background-size:32px_32px]"
          aria-hidden
        />
        <div className="relative">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary-foreground/70">Ready / Deploy</p>
          <h2 className="mt-3 max-w-xl text-3xl font-semibold tracking-tight">{copy.ctaTitle}</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-primary-foreground/80">{copy.ctaBody}</p>
          <div className="mt-6">
            <Link
              href="/register"
              className="inline-flex h-10 items-center rounded-md bg-background px-4 text-sm font-medium text-foreground"
            >
              {copy.register}
            </Link>
          </div>
        </div>
      </section>
    </SiteShell>
  );
}
