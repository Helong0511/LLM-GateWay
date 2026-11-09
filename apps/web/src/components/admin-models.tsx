"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
  infoFlash,
  loadFlash,
  okFlash,
  resultFlash,
  warnFlash,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { RefreshButton } from "@/components/ui/refresh-button";
import { errorMessage, getJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

const PAGE_SIZES = [20, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 20;

async function pullModels(loadFail: string): Promise<{ items: CatalogModel[]; message: string }> {
  const result = await getJson("/api/admin/models");
  if (!result.ok || !result.envelope.data) {
    return { items: [], message: errorMessage(result.envelope, loadFail) };
  }
  return { items: readModels(result.envelope.data.models), message: "" };
}

type CatalogModel = {
  id: string;
  provider_id: string;
  provider_name: string;
  display_name: string;
  public_name: string;
  upstream_name: string;
  status: string;
  supports_stream: boolean | null;
  supports_embeddings: boolean | null;
  upstream_input_price: string | null;
  upstream_output_price: string | null;
};

type StatusFilter = "pending" | "published" | "disabled" | "all";
type CapabilityFilter = "all" | "stream" | "no_stream" | "embeddings" | "no_embeddings";
type PriceFilter = "all" | "has" | "none";
type SortKey = "default" | "name" | "provider";

function modelName(item: CatalogModel): string {
  return item.display_name || item.public_name || item.upstream_name;
}

function matchesCapability(item: CatalogModel, filter: CapabilityFilter): boolean {
  switch (filter) {
    case "stream":
      return item.supports_stream !== false;
    case "no_stream":
      return item.supports_stream === false;
    case "embeddings":
      return item.supports_embeddings === true;
    case "no_embeddings":
      return item.supports_embeddings !== true;
    default:
      return true;
  }
}

function matchesPrice(item: CatalogModel, filter: PriceFilter): boolean {
  const hasPrice = item.upstream_input_price !== null || item.upstream_output_price !== null;
  if (filter === "has") {
    return hasPrice;
  }
  if (filter === "none") {
    return !hasPrice;
  }
  return true;
}

function sortModels(rows: CatalogModel[], key: SortKey): CatalogModel[] {
  if (key === "default") {
    return rows;
  }
  const copy = [...rows];
  if (key === "name") {
    copy.sort((a, b) => modelName(a).localeCompare(modelName(b)));
    return copy;
  }
  copy.sort(
    (a, b) =>
      a.provider_name.localeCompare(b.provider_name) || modelName(a).localeCompare(modelName(b)),
  );
  return copy;
}

export function AdminModels() {
  const { t } = useI18n();
  const m = t.admin.pages.models;
  const [models, setModels] = useState<CatalogModel[]>([]);
  const { flash, setFlash } = useBootFlash(m.loading);
  const [busy, setBusy] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const [providerFilter, setProviderFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [capabilityFilter, setCapabilityFilter] = useState<CapabilityFilter>("all");
  const [priceFilter, setPriceFilter] = useState<PriceFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("default");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [editing, setEditing] = useState<CatalogModel | null>(null);

  async function load() {
    const next = await pullModels(m.loadFail);
    setModels(next.items);
    setFlash(loadFlash(next.message));
    setSelected((prev) => {
      const ids = new Set(next.items.map((item) => item.id));
      return new Set([...prev].filter((id) => ids.has(id)));
    });
    setProviderFilter((prev) => {
      if (prev === "all") {
        return prev;
      }
      return next.items.some((item) => item.provider_id === prev) ? prev : "all";
    });
  }

  useEffect(() => {
    void (async () => {
      const next = await pullModels(m.loadFail);
      setModels(next.items);
      setFlash(loadFlash(next.message));
      setSelected((prev) => {
        const ids = new Set(next.items.map((item) => item.id));
        return new Set([...prev].filter((id) => ids.has(id)));
      });
      setProviderFilter((prev) => {
        if (prev === "all") {
          return prev;
        }
        return next.items.some((item) => item.provider_id === prev) ? prev : "all";
      });
    })();
  }, []);

  const providers = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of models) {
      if (!item.provider_id) {
        continue;
      }
      if (!map.has(item.provider_id)) {
        map.set(item.provider_id, item.provider_name || item.provider_id);
      }
    }
    return [...map.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
  }, [models]);

  /** 供应商 / 搜索 / 能力 / 上游价：状态计数与列表都基于这份结果，避免分页与计数口径不一致。 */
  const base = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return models.filter((item) => {
      if (providerFilter !== "all" && item.provider_id !== providerFilter) {
        return false;
      }
      if (!matchesCapability(item, capabilityFilter) || !matchesPrice(item, priceFilter)) {
        return false;
      }
      if (!needle) {
        return true;
      }
      const hay =
        `${item.public_name} ${item.display_name} ${item.upstream_name} ${item.provider_name}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [models, providerFilter, query, capabilityFilter, priceFilter]);

  const counts = useMemo(
    () => ({
      pending: base.filter((item) => item.status === "pending").length,
      published: base.filter((item) => item.status === "published").length,
      disabled: base.filter((item) => item.status === "disabled").length,
      all: base.length,
    }),
    [base],
  );

  const filtered = useMemo(() => {
    const rows =
      statusFilter === "all" ? base : base.filter((item) => item.status === statusFilter);
    return sortModels(rows, sortKey);
  }, [base, statusFilter, sortKey]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / Math.max(pageSize, 1)));
  const currentPage = Math.min(page, totalPages);

  const pageRows = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, currentPage, pageSize]);

  const hasFilters =
    providerFilter !== "all" ||
    query.trim() !== "" ||
    capabilityFilter !== "all" ||
    priceFilter !== "all";

  function changeFilter(apply: () => void) {
    apply();
    setPage(1);
    setSelected(new Set());
  }

  function toggleOne(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }

  function selectPage() {
    setSelected(new Set(pageRows.map((item) => item.id)));
  }

  function selectAllFiltered() {
    setSelected(new Set(filtered.map((item) => item.id)));
  }

  function clearSelection() {
    setSelected(new Set());
  }

  async function publish(model: CatalogModel, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      display_name: String(form.get("display_name") ?? model.display_name),
      supports_stream: form.get("supports_stream") === "on",
      supports_embeddings: form.get("supports_embeddings") === "on",
    };
    setBusy(true);
    const result = await postJson(`/api/admin/models/${model.id}/publish`, payload);
    setBusy(false);
    setFlash(resultFlash(result.ok, m.msg.published, apiErrorLabel(t, result.envelope, m.msg.publishFail)));
    if (result.ok) {
      setEditing(null);
      await load();
    }
  }

  async function batchPublish() {
    // 与后端一致：只跳过已上架，待上架与已下架都执行上架（已下架会恢复部署）。
    const ids = [...selected].filter(
      (id) => models.some((item) => item.id === id && item.status !== "published"),
    );
    if (ids.length === 0) {
      setFlash(warnFlash(m.msg.batchNeedSelection));
      return;
    }
    if (!window.confirm(m.msg.confirmBatchPublish.replace("{count}", String(ids.length)))) {
      return;
    }
    setBusy(true);
    const result = await postJson("/api/admin/models/publish-batch", {
      model_ids: ids,
      supports_stream: true,
      supports_embeddings: false,
    });
    setBusy(false);
    if (!result.ok || !result.envelope.data) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, m.msg.batchPublishFail)));
      return;
    }
    const data = result.envelope.data;
    setFlash(
      okFlash(
        m.msg.batchPublished
          .replace("{published}", String(data.published ?? 0))
          .replace("{skipped}", String(data.skipped ?? 0))
          .replace("{missing}", String(data.missing ?? 0)),
      ),
    );
    setSelected(new Set());
    changeFilter(() => setStatusFilter("published"));
    await load();
  }

  async function batchUnpublish() {
    const ids = [...selected].filter(
      (id) => models.some((item) => item.id === id && item.status === "published"),
    );
    if (ids.length === 0) {
      setFlash(warnFlash(m.msg.batchUnpublishNeedSelection));
      return;
    }
    if (!window.confirm(m.msg.confirmBatchUnpublish.replace("{count}", String(ids.length)))) {
      return;
    }
    setBusy(true);
    const result = await postJson("/api/admin/models/unpublish-batch", { model_ids: ids });
    setBusy(false);
    if (!result.ok || !result.envelope.data) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, m.msg.batchUnpublishFail)));
      return;
    }
    const data = result.envelope.data;
    setFlash(
      okFlash(
        m.msg.batchUnpublished
          .replace("{unpublished}", String(data.unpublished ?? 0))
          .replace("{skipped}", String(data.skipped ?? 0))
          .replace("{missing}", String(data.missing ?? 0)),
      ),
    );
    setSelected(new Set());
    changeFilter(() => setStatusFilter("disabled"));
    await load();
  }

  async function price(modelId: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const input = String(form.get("input_price") ?? "");
    const output = String(form.get("output_price") ?? "");
    const payload = {
      model_id: modelId,
      meters: [
        { meter: "input_token", unit_price: input, cost_price: input, min_billable_units: 0 },
        { meter: "output_token", unit_price: output, cost_price: output, min_billable_units: 0 },
      ],
    };
    setBusy(true);
    const result = await postJson("/api/admin/prices", payload);
    setBusy(false);
    setFlash(resultFlash(result.ok, m.msg.pricePublished, apiErrorLabel(t, result.envelope, m.msg.pricePublishFail)));
    if (result.ok) {
      setEditing(null);
    }
  }

  async function unpublish(model: CatalogModel) {
    const name = modelName(model);
    if (!window.confirm(m.msg.confirmUnpublish.replace("{name}", name))) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/models/${model.id}/unpublish`, {});
    setBusy(false);
    setFlash(
      resultFlash(result.ok, m.msg.unpublished, apiErrorLabel(t, result.envelope, m.msg.unpublishFail)),
    );
    if (result.ok) {
      changeFilter(() => setStatusFilter("disabled"));
      await load();
    }
  }

  async function showPrices(modelId: string) {
    setBusy(true);
    const result = await getJson(`/api/admin/prices?model_id=${modelId}`);
    setBusy(false);
    if (!result.ok || !result.envelope.data || !Array.isArray(result.envelope.data.prices)) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, m.msg.priceLoadFail)));
      return;
    }
    const rows = result.envelope.data.prices as Array<Record<string, unknown>>;
    if (rows.length === 0) {
      setFlash(warnFlash(m.msg.noPrice));
      return;
    }
    setFlash(
      infoFlash(
        rows
          .slice(0, 5)
          .map(
            (row) =>
              `${String(row.version)} · ${row.active === true ? m.priceActive : m.priceHistory} · ${String(row.currency)}`,
          )
          .join("；"),
      ),
    );
  }

  const emptyText = hasFilters
    ? m.emptyFiltered
    : statusFilter === "pending"
      ? m.emptyPending
      : statusFilter === "published"
        ? m.emptyPublished
        : statusFilter === "disabled"
          ? m.emptyDisabled
          : m.emptyAll;

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{m.title}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground/70">{m.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>

      <div className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-sm">
          {m.providerFilter}
          <select
            value={providerFilter}
            onChange={(event) => changeFilter(() => setProviderFilter(event.target.value))}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
          >
            <option value="all">{m.providerAll}</option>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          {m.filterCapability}
          <select
            value={capabilityFilter}
            onChange={(event) =>
              changeFilter(() => setCapabilityFilter(event.target.value as CapabilityFilter))
            }
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
          >
            <option value="all">{m.capabilityAll}</option>
            <option value="stream">{m.capabilityStream}</option>
            <option value="no_stream">{m.capabilityNoStream}</option>
            <option value="embeddings">{m.capabilityEmbeddings}</option>
            <option value="no_embeddings">{m.capabilityNoEmbeddings}</option>
          </select>
        </label>
        <label className="text-sm">
          {m.filterPrice}
          <select
            value={priceFilter}
            onChange={(event) => changeFilter(() => setPriceFilter(event.target.value as PriceFilter))}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
          >
            <option value="all">{m.priceAny}</option>
            <option value="has">{m.priceHas}</option>
            <option value="none">{m.priceNone}</option>
          </select>
        </label>
        <label className="text-sm">
          {m.search}
          <input
            value={query}
            onChange={(event) => changeFilter(() => setQuery(event.target.value))}
            placeholder={m.searchPlaceholder}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
          />
        </label>
        <div className="flex items-end gap-2">
          <label className="flex-1 text-sm">
            {m.sort}
            <select
              value={sortKey}
              onChange={(event) => {
                setSortKey(event.target.value as SortKey);
                setPage(1);
              }}
              className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            >
              <option value="default">{m.sortDefault}</option>
              <option value="name">{m.sortName}</option>
              <option value="provider">{m.sortProvider}</option>
            </select>
          </label>
          <button
            type="button"
            className="rounded border border-border px-2 py-1.5 text-sm"
            disabled={
              providerFilter === "all" &&
              query.trim() === "" &&
              capabilityFilter === "all" &&
              priceFilter === "all"
            }
            onClick={() =>
              changeFilter(() => {
                setProviderFilter("all");
                setCapabilityFilter("all");
                setPriceFilter("all");
                setQuery("");
                setSortKey("default");
              })
            }
          >
            {m.resetFilters}
          </button>
        </div>
      </div>
      <p className="text-xs text-foreground/60">{m.searchHint}</p>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {(["pending", "published", "disabled", "all"] as const).map((value) => {
          const label = value === "all" ? t.labels.common.all : statusLabel(t, "model", value);
          const count = counts[value];
          const active = statusFilter === value;
          return (
            <button
              key={value}
              type="button"
              className={
                active
                  ? "rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-accent"
                  : "rounded border border-border px-3 py-1.5 text-foreground/75"
              }
              onClick={() => changeFilter(() => setStatusFilter(value))}
            >
              {label}（{count}）
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button
          type="button"
          disabled={busy || pageRows.length === 0}
          className="rounded border border-border px-3 py-1.5"
          onClick={selectPage}
        >
          {m.selectAllPage}
        </button>
        <button
          type="button"
          disabled={busy || filtered.length === 0}
          className="rounded border border-border px-3 py-1.5"
          onClick={selectAllFiltered}
        >
          {m.selectAllFiltered.replace("{count}", String(filtered.length))}
        </button>
        <button
          type="button"
          disabled={busy || selected.size === 0}
          className="rounded border border-border px-3 py-1.5"
          onClick={clearSelection}
        >
          {m.clearSelection}
        </button>
        <button
          type="button"
          disabled={busy || selected.size === 0}
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
          onClick={() => void batchPublish()}
        >
          {m.batchPublish}
        </button>
        <button
          type="button"
          disabled={busy || selected.size === 0}
          className="rounded border border-border px-3 py-1.5"
          onClick={() => void batchUnpublish()}
        >
          {m.batchUnpublish}
        </button>
        <span className="text-foreground/70">{m.selectedCount.replace("{count}", String(selected.size))}</span>
      </div>

      {filtered.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-foreground/70">
          {emptyText}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[940px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-left text-xs text-foreground/60">
                <th className="w-10 px-3 py-2">
                  <span className="sr-only">select</span>
                </th>
                <th className="px-3 py-2 font-medium">{m.columnModel}</th>
                <th className="px-3 py-2 font-medium">{m.columnProvider}</th>
                <th className="px-3 py-2 font-medium">{m.columnStatus}</th>
                <th className="px-3 py-2 font-medium">{m.columnCapabilities}</th>
                <th className="px-3 py-2 text-right font-medium">{m.columnUpstreamPrice}</th>
                <th className="px-3 py-2 text-right font-medium">{m.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((model) => (
                <tr key={model.id} className="border-b border-border/70 last:border-b-0 hover:bg-muted/20">
                  <td className="px-3 py-2 align-middle">
                    <input
                      type="checkbox"
                      checked={selected.has(model.id)}
                      onChange={(event) => toggleOne(model.id, event.target.checked)}
                      aria-label={modelName(model)}
                    />
                  </td>
                  <td className="max-w-[280px] px-3 py-2 align-middle">
                    <p className="truncate font-medium">{modelName(model)}</p>
                    <p className="truncate text-xs text-foreground/60">
                      {model.public_name} / {model.upstream_name}
                    </p>
                  </td>
                  <td className="max-w-[140px] truncate px-3 py-2 align-middle text-foreground/80">
                    {model.provider_name || "—"}
                  </td>
                  <td className="px-3 py-2 align-middle">
                    <span
                      className={
                        model.status === "published"
                          ? "text-[hsl(var(--success-fg))]"
                          : model.status === "disabled"
                            ? "text-[hsl(var(--warning-fg))]"
                            : "text-foreground/70"
                      }
                    >
                      {statusLabel(t, "model", model.status)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 align-middle text-xs text-foreground/70">
                    {model.supports_stream !== false || model.supports_embeddings === true ? (
                      <>
                        {model.supports_stream !== false ? m.stream : null}
                        {model.supports_stream !== false && model.supports_embeddings === true ? (
                          <span className="text-foreground/40"> · </span>
                        ) : null}
                        {model.supports_embeddings === true ? m.embeddings : null}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 align-middle text-right tabular-nums text-xs text-foreground/70">
                    {model.upstream_input_price || model.upstream_output_price ? (
                      <>
                        {model.upstream_input_price ?? "—"} / {model.upstream_output_price ?? "—"}
                      </>
                    ) : (
                      <span className="text-foreground/45">{m.upstreamUnset}</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 align-middle text-right">
                    <div className="flex justify-end gap-1.5">
                      <button
                        type="button"
                        disabled={busy}
                        className="rounded border border-border px-2 py-1 text-xs"
                        onClick={() => setEditing(model)}
                      >
                        {model.status === "published" ? m.editAction : t.admin.actions.publish}
                      </button>
                      {model.status === "published" ? (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-border px-2 py-1 text-xs"
                          onClick={() => void unpublish(model)}
                        >
                          {t.admin.actions.unpublish}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        disabled={busy}
                        className="rounded border border-border px-2 py-1 text-xs"
                        onClick={() => void showPrices(model.id)}
                      >
                        {m.priceVersions}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-foreground/70">
          {m.pageSize}
          <select
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
            className="rounded border border-border bg-transparent px-2 py-1"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {m.pageSizeUnit.replace("{count}", String(size))}
              </option>
            ))}
          </select>
        </label>
        <PageControls page={currentPage} pageSize={pageSize} total={filtered.length} onPageChange={setPage} />
      </div>

      {editing ? (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="model-edit-title"
          onClick={() => setEditing(null)}
        >
          <div
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-border bg-background p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="model-edit-title" className="text-lg font-semibold tracking-tight">
                  {m.dialogTitle}
                </h2>
                <p className="mt-1 text-sm font-medium">{modelName(editing)}</p>
                <p className="text-xs text-foreground/60">
                  {editing.provider_name || "—"} · {editing.public_name} / {editing.upstream_name}
                </p>
              </div>
              <button
                type="button"
                className="rounded px-2 text-lg leading-none opacity-70 hover:opacity-100"
                aria-label={t.admin.actions.close}
                onClick={() => setEditing(null)}
              >
                ×
              </button>
            </div>
            <p className="mt-3 text-sm leading-6 text-foreground/70">{m.dialogLead}</p>

            <form className="mt-4 space-y-3" onSubmit={(event) => void publish(editing, event)}>
              <label className="block text-sm">
                {m.displayName}
                <input
                  name="display_name"
                  defaultValue={editing.display_name || modelName(editing)}
                  required
                  className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2"
                />
              </label>
              <div className="flex flex-wrap gap-4 text-sm">
                <label className="flex items-center gap-2">
                  <input name="supports_stream" type="checkbox" defaultChecked={editing.supports_stream !== false} />
                  {m.stream}
                </label>
                <label className="flex items-center gap-2">
                  <input
                    name="supports_embeddings"
                    type="checkbox"
                    defaultChecked={editing.supports_embeddings === true}
                  />
                  {m.embeddings}
                </label>
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={busy}
                  className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
                >
                  {editing.status === "published" ? m.saveAction : t.admin.actions.publish}
                </button>
              </div>
            </form>

            <div className="mt-4 border-t border-border pt-4">
              <form className="space-y-3" onSubmit={(event) => void price(editing.id, event)}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-sm">
                    {m.inputPrice}
                    <span className="mt-0.5 block text-xs text-foreground/60">
                      {editing.upstream_input_price ? m.upstreamPriceHint : m.inputPriceHint}
                    </span>
                    <input
                      name="input_price"
                      required
                      defaultValue={editing.upstream_input_price ?? ""}
                      placeholder="0.00000100"
                      className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2"
                    />
                  </label>
                  <label className="text-sm">
                    {m.outputPrice}
                    <span className="mt-0.5 block text-xs text-foreground/60">
                      {editing.upstream_output_price ? m.upstreamPriceHint : m.outputPriceHint}
                    </span>
                    <input
                      name="output_price"
                      required
                      defaultValue={editing.upstream_output_price ?? ""}
                      placeholder="0.00000200"
                      className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2"
                    />
                  </label>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded border border-border px-3 py-1.5 text-sm"
                    onClick={() => void showPrices(editing.id)}
                  >
                    {m.priceVersions}
                  </button>
                  <button
                    type="submit"
                    disabled={busy}
                    className="rounded border border-border px-3 py-1.5 text-sm"
                  >
                    {t.admin.actions.publishPrice}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function readModels(value: unknown): CatalogModel[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.status !== "string") {
      return [];
    }
    return [
      {
        id: row.id,
        provider_id: typeof row.provider_id === "string" ? row.provider_id : "",
        provider_name: typeof row.provider_name === "string" ? row.provider_name : "",
        display_name: typeof row.display_name === "string" ? row.display_name : "",
        public_name: typeof row.public_name === "string" ? row.public_name : "",
        upstream_name: typeof row.upstream_name === "string" ? row.upstream_name : "",
        status: row.status,
        supports_stream: typeof row.supports_stream === "boolean" ? row.supports_stream : null,
        supports_embeddings:
          typeof row.supports_embeddings === "boolean" ? row.supports_embeddings : null,
        upstream_input_price:
          typeof row.upstream_input_price === "string" ? row.upstream_input_price : null,
        upstream_output_price:
          typeof row.upstream_output_price === "string" ? row.upstream_output_price : null,
      },
    ];
  });
}
