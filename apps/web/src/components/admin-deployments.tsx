"use client";

import { useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
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

type Deployment = {
  id: string;
  modelId: string;
  publicName: string;
  displayName: string;
  providerId: string;
  providerName: string;
  status: string;
  modelStatus: string;
};

type StatusFilter = "active" | "disabled" | "all";
type SortKey = "default" | "name" | "provider";

async function pullDeployments(loadFail: string): Promise<{ rows: Deployment[]; message: string }> {
  const result = await getJson("/api/admin/deployments");
  if (!result.ok || !result.envelope.data) {
    return { rows: [], message: errorMessage(result.envelope, loadFail) };
  }
  return { rows: readRows(result.envelope.data.deployments), message: "" };
}

function deploymentName(row: Deployment): string {
  return row.displayName || row.publicName;
}

function sortRows(rows: Deployment[], key: SortKey): Deployment[] {
  if (key === "default") {
    return rows;
  }
  const copy = [...rows];
  if (key === "name") {
    copy.sort((a, b) => deploymentName(a).localeCompare(deploymentName(b)));
    return copy;
  }
  copy.sort(
    (a, b) =>
      a.providerName.localeCompare(b.providerName) ||
      deploymentName(a).localeCompare(deploymentName(b)),
  );
  return copy;
}

export function AdminDeployments() {
  const { t } = useI18n();
  const d = t.admin.pages.deployments;
  const [rows, setRows] = useState<Deployment[]>([]);
  const { flash, setFlash } = useBootFlash(d.loading);
  const [busy, setBusy] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [providerFilter, setProviderFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());

  async function load() {
    const next = await pullDeployments(d.loadFail);
    setRows(next.rows);
    setFlash(loadFlash(next.message));
    setSelected((prev) => {
      const ids = new Set(next.rows.map((item) => item.id));
      return new Set([...prev].filter((id) => ids.has(id)));
    });
    setProviderFilter((prev) => {
      if (prev === "all") {
        return prev;
      }
      return next.rows.some((item) => item.providerId === prev) ? prev : "all";
    });
  }

  useEffect(() => {
    void (async () => {
      const next = await pullDeployments(d.loadFail);
      setRows(next.rows);
      setFlash(loadFlash(next.message));
      setSelected((prev) => {
        const ids = new Set(next.rows.map((item) => item.id));
        return new Set([...prev].filter((id) => ids.has(id)));
      });
      setProviderFilter((prev) => {
        if (prev === "all") {
          return prev;
        }
        return next.rows.some((item) => item.providerId === prev) ? prev : "all";
      });
    })();
  }, []);

  const providers = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of rows) {
      if (!row.providerId) {
        continue;
      }
      if (!map.has(row.providerId)) {
        map.set(row.providerId, row.providerName || row.providerId);
      }
    }
    return [...map.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
  }, [rows]);

  /** 供应商 + 搜索：状态计数与列表共用同一口径，保证分页总数不丢项。 */
  const base = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (providerFilter !== "all" && row.providerId !== providerFilter) {
        return false;
      }
      if (!needle) {
        return true;
      }
      const hay = `${row.publicName} ${row.displayName} ${row.providerName}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [rows, providerFilter, query]);

  const counts = useMemo(
    () => ({
      active: base.filter((row) => row.status === "active").length,
      disabled: base.filter((row) => row.status === "disabled").length,
      all: base.length,
    }),
    [base],
  );

  const filtered = useMemo(() => {
    const scoped =
      statusFilter === "all" ? base : base.filter((row) => row.status === statusFilter);
    return sortRows(scoped, sortKey);
  }, [base, statusFilter, sortKey]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / Math.max(pageSize, 1)));
  const currentPage = Math.min(page, totalPages);

  const pageRows = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, currentPage, pageSize]);

  const hasFilters = providerFilter !== "all" || query.trim() !== "";

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

  async function toggle(row: Deployment) {
    const status = row.status === "active" ? "disabled" : "active";
    if (status === "disabled") {
      const ok = window.confirm(
        d.msg.confirmDisable.replace("{name}", deploymentName(row)),
      );
      if (!ok) {
        return;
      }
    }
    if (status === "active" && row.modelStatus !== "published") {
      setFlash(warnFlash(d.msg.enableBlocked));
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/deployments/${row.id}/status`, { status });
    setBusy(false);
    setFlash(
      resultFlash(
        result.ok,
        status === "disabled" ? d.msg.disabled : d.msg.enabled,
        apiErrorLabel(t, result.envelope, d.msg.statusFail),
      ),
    );
    if (result.ok) {
      await load();
    }
  }

  async function batchStatus(status: "active" | "disabled") {
    const selectedRows = rows.filter((row) => selected.has(row.id));
    if (selectedRows.length === 0) {
      setFlash(warnFlash(d.msg.batchNeedSelection));
      return;
    }
    // 启用时模型未上架的部署无法真正调用，先剔除并计入提示。
    const blockedRows =
      status === "active" ? selectedRows.filter((row) => row.modelStatus !== "published") : [];
    const ids = selectedRows
      .filter((row) => !blockedRows.includes(row))
      .map((row) => row.id);
    if (ids.length === 0) {
      setFlash(warnFlash(d.msg.batchEnableBlocked));
      return;
    }
    let confirmText =
      status === "disabled"
        ? d.msg.confirmBatchDisable.replace("{count}", String(ids.length))
        : d.msg.confirmBatchEnable.replace("{count}", String(ids.length));
    if (blockedRows.length > 0) {
      confirmText += d.msg.batchEnableBlockedPart.replace("{blocked}", String(blockedRows.length));
    }
    if (!window.confirm(confirmText)) {
      return;
    }
    setBusy(true);
    const result = await postJson("/api/admin/deployments/status-batch", {
      deployment_ids: ids,
      status,
    });
    setBusy(false);
    if (!result.ok || !result.envelope.data) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, d.msg.batchFail)));
      return;
    }
    const data = result.envelope.data;
    const template = status === "disabled" ? d.msg.batchDisabled : d.msg.batchEnabled;
    setFlash(
      okFlash(
        template
          .replace("{updated}", String(data.updated ?? 0))
          .replace("{skipped}", String(data.skipped ?? 0))
          .replace("{missing}", String(data.missing ?? 0))
          .replace("{blocked}", String(Number(data.blocked ?? 0) + blockedRows.length)),
      ),
    );
    setSelected(new Set());
    changeFilter(() => setStatusFilter(status === "disabled" ? "disabled" : "active"));
    await load();
  }

  const emptyText = hasFilters
    ? d.emptyFiltered
    : statusFilter === "active"
      ? d.emptyActive
      : statusFilter === "disabled"
        ? d.emptyDisabled
        : d.emptyAll;

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{d.title}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground/70">{d.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>

      <div className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm">
          {d.providerFilter}
          <select
            value={providerFilter}
            onChange={(event) => changeFilter(() => setProviderFilter(event.target.value))}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
          >
            <option value="all">{d.providerAll}</option>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          {d.search}
          <input
            value={query}
            onChange={(event) => changeFilter(() => setQuery(event.target.value))}
            placeholder={d.searchPlaceholder}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
          />
        </label>
        <label className="text-sm">
          {d.sort}
          <select
            value={sortKey}
            onChange={(event) => {
              setSortKey(event.target.value as SortKey);
              setPage(1);
            }}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
          >
            <option value="default">{d.sortDefault}</option>
            <option value="name">{d.sortName}</option>
            <option value="provider">{d.sortProvider}</option>
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="button"
            className="rounded border border-border px-2 py-1.5 text-sm"
            disabled={providerFilter === "all" && query.trim() === ""}
            onClick={() =>
              changeFilter(() => {
                setProviderFilter("all");
                setQuery("");
                setSortKey("default");
              })
            }
          >
            {d.resetFilters}
          </button>
        </div>
      </div>
      <p className="text-xs text-foreground/60">{d.searchHint}</p>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {(["active", "disabled", "all"] as const).map((value) => {
          const label = value === "all" ? t.labels.common.all : statusLabel(t, "deployment", value);
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
          {d.selectAllPage}
        </button>
        <button
          type="button"
          disabled={busy || filtered.length === 0}
          className="rounded border border-border px-3 py-1.5"
          onClick={selectAllFiltered}
        >
          {d.selectAllFiltered.replace("{count}", String(filtered.length))}
        </button>
        <button
          type="button"
          disabled={busy || selected.size === 0}
          className="rounded border border-border px-3 py-1.5"
          onClick={clearSelection}
        >
          {d.clearSelection}
        </button>
        <button
          type="button"
          disabled={busy || selected.size === 0}
          className="rounded border border-border px-3 py-1.5"
          onClick={() => void batchStatus("disabled")}
        >
          {d.batchDisable}
        </button>
        <button
          type="button"
          disabled={busy || selected.size === 0}
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
          onClick={() => void batchStatus("active")}
        >
          {d.batchEnable}
        </button>
        <span className="text-foreground/70">{d.selectedCount.replace("{count}", String(selected.size))}</span>
      </div>

      {filtered.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-foreground/70">
          {emptyText}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-left text-xs text-foreground/60">
                <th className="w-10 px-3 py-2">
                  <span className="sr-only">select</span>
                </th>
                <th className="px-3 py-2 font-medium">{d.columnDeployment}</th>
                <th className="px-3 py-2 font-medium">{d.columnProvider}</th>
                <th className="px-3 py-2 font-medium">{d.columnStatus}</th>
                <th className="px-3 py-2 text-right font-medium">{d.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => (
                <tr key={row.id} className="border-b border-border/70 last:border-b-0 hover:bg-muted/20">
                  <td className="px-3 py-2 align-middle">
                    <input
                      type="checkbox"
                      checked={selected.has(row.id)}
                      onChange={(event) => toggleOne(row.id, event.target.checked)}
                      aria-label={deploymentName(row)}
                    />
                  </td>
                  <td className="max-w-[320px] px-3 py-2 align-middle">
                    <p className="truncate font-medium">{deploymentName(row)}</p>
                    <p className="truncate text-xs text-foreground/60">{row.publicName}</p>
                  </td>
                  <td className="max-w-[160px] truncate px-3 py-2 align-middle text-foreground/80">
                    {row.providerName || "—"}
                  </td>
                  <td className="px-3 py-2 align-middle">
                    <span
                      className={
                        row.status === "active"
                          ? "text-[hsl(var(--success-fg))]"
                          : "text-[hsl(var(--warning-fg))]"
                      }
                    >
                      {statusLabel(t, "deployment", row.status)}
                    </span>
                    {row.modelStatus !== "published" ? (
                      <span className="mt-0.5 block text-xs text-foreground/50">{d.modelUnpublished}</span>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 align-middle text-right">
                    <button
                      type="button"
                      disabled={busy || (row.status !== "active" && row.modelStatus !== "published")}
                      className="rounded border border-border px-2 py-1 text-xs disabled:opacity-40"
                      onClick={() => void toggle(row)}
                    >
                      {row.status === "active" ? t.admin.actions.disable : t.admin.actions.enable}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-foreground/70">
          {d.pageSize}
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
                {d.pageSizeUnit.replace("{count}", String(size))}
              </option>
            ))}
          </select>
        </label>
        <PageControls page={currentPage} pageSize={pageSize} total={filtered.length} onPageChange={setPage} />
      </div>
    </section>
  );
}

function readRows(value: unknown): Deployment[] {
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
        modelId: typeof row.model_id === "string" ? row.model_id : "",
        publicName: typeof row.public_name === "string" ? row.public_name : "",
        displayName: typeof row.display_name === "string" ? row.display_name : "",
        providerId: typeof row.provider_id === "string" ? row.provider_id : "",
        providerName: typeof row.provider_name === "string" ? row.provider_name : "",
        status: row.status,
        modelStatus: typeof row.model_status === "string" ? row.model_status : "",
      },
    ];
  });
}
