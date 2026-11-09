"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import { FlashBanner, errFlash, infoFlash, type FlashMessage } from "@/components/ui/flash";
import { getJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";

type CatalogModel = {
  id: string;
  display_name: string;
  public_name: string;
  supports_stream: boolean | null;
  supports_embeddings: boolean | null;
  supports_tools: boolean | null;
  supports_vision: boolean | null;
  supports_images: boolean | null;
  context_window: number | null;
  max_output: number | null;
};

function readModel(value: unknown): CatalogModel | null {
  if (typeof value !== "object" || value === null) return null;
  const row = value as Record<string, unknown>;
  if (typeof row.id !== "string" || typeof row.public_name !== "string") return null;
  return {
    id: row.id,
    display_name: typeof row.display_name === "string" ? row.display_name : row.public_name,
    public_name: row.public_name,
    supports_stream: typeof row.supports_stream === "boolean" ? row.supports_stream : null,
    supports_embeddings: typeof row.supports_embeddings === "boolean" ? row.supports_embeddings : null,
    supports_tools: typeof row.supports_tools === "boolean" ? row.supports_tools : null,
    supports_vision: typeof row.supports_vision === "boolean" ? row.supports_vision : null,
    supports_images: typeof row.supports_images === "boolean" ? row.supports_images : null,
    context_window: typeof row.context_window === "number" ? row.context_window : null,
    max_output: typeof row.max_output === "number" ? row.max_output : null,
  };
}

export function ModelsPanel() {
  const { t } = useI18n();
  const m = t.console.models;
  const { flash, setFlash } = useBootFlash(t.console.models.loading);
  const [models, setModels] = useState<CatalogModel[] | null>(null);

  function flag(value: boolean | null): string {
    if (value === true) return m.supported;
    if (value === false) return m.unsupported;
    return m.unconfirmed;
  }

  function numberOrUnknown(value: number | null): string {
    return value === null ? m.unconfirmed : String(value);
  }

  useEffect(() => {
    void (async () => {
      const result = await getJson("/api/console/models");
      if (!result.ok) {
        setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.models.loadFail)));
        setModels([]);
        return;
      }
      const rows = result.envelope.data?.models;
      setModels(Array.isArray(rows) ? rows.map(readModel).filter((item): item is CatalogModel => item !== null) : []);
      setFlash(infoFlash(t.console.models.publishedOnly));
    })();
  }, []);

  return (
    <section className="max-w-3xl space-y-3">
      <h1 className="text-3xl font-semibold tracking-tight">{m.title}</h1>
      <p className="text-sm text-foreground/70">{m.lead}</p>
      {flash ? <FlashBanner flash={flash} compact /> : null}
      {models && models.length === 0 ? <p className="text-sm">{m.empty}</p> : null}
      {models && models.length > 0 ? (
        <ul className="space-y-3">
          {models.map((model) => (
            <li key={model.id} className="rounded-md border border-border px-3 py-3 text-sm">
              <p className="font-medium">{model.display_name}</p>
              <p className="text-foreground/70">
                {m.callName} {model.public_name}
              </p>
              <p>
                {m.stream} {flag(model.supports_stream)}，{m.embeddings} {flag(model.supports_embeddings)}
              </p>
              <p>
                {m.tools} {flag(model.supports_tools)}，{m.vision} {flag(model.supports_vision)}，{m.images}{" "}
                {flag(model.supports_images)}
              </p>
              <p>
                {m.context} {numberOrUnknown(model.context_window)}，{m.maxOutput} {numberOrUnknown(model.max_output)}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
