"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  loadFlash,
  resultFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { RefreshButton } from "@/components/ui/refresh-button";
import { errorMessage, getJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

const PAGE_SIZE = 20;

type AdminKey = {
  id: string;
  email: string;
  name: string;
  keyPrefix: string;
  status: string;
  rpm: string;
  tpm: string;
  concurrency: string;
  budget: string;
  /** 账号级有效模型；null 表示不限。 */
  effectiveModels: string[] | null;
};

async function pullKeys(
  page: number,
  filters: { q: string; status: string },
  loadFail: string,
): Promise<{ keys: AdminKey[]; total: number; message: string }> {
  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (filters.q.trim()) {
    params.set("q", filters.q.trim());
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  const result = await getJson(`/api/admin/keys?${params.toString()}`);
  if (!result.ok || !result.envelope.data) {
    return { keys: [], total: 0, message: errorMessage(result.envelope, loadFail) };
  }
  return {
    keys: readKeys(result.envelope.data.keys),
    total: typeof result.envelope.data.total === "number" ? result.envelope.data.total : 0,
    message: "",
  };
}

export function AdminKeys() {
  const { t } = useI18n();
  const [keys, setKeys] = useState<AdminKey[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { flash, setFlash } = useBootFlash(t.admin.pages.keys.loading);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [appliedStatus, setAppliedStatus] = useState("");

  async function load() {
    const next = await pullKeys(page, { q: appliedQ, status: appliedStatus }, t.admin.pages.keys.loadFail);
    setKeys(next.keys);
    setTotal(next.total);
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullKeys(page, { q: appliedQ, status: appliedStatus }, t.admin.pages.keys.loadFail);
      setKeys(next.keys);
      setTotal(next.total);
      setFlash(loadFlash(next.message));
    })();
  }, [page, appliedQ, appliedStatus]);

  async function revoke(row: AdminKey) {
    if (!window.confirm(t.admin.pages.keys.msg.confirmRevoke.replace("{email}", row.email).replace("{prefix}", row.keyPrefix))) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/keys/${row.id}/revoke`, {});
    setBusy(false);
    setFlash(resultFlash(result.ok, t.admin.pages.keys.msg.revoked, apiErrorLabel(t, result.envelope, t.admin.pages.keys.msg.revokeFail)));
    if (result.ok) {
      await load();
    }
  }

  async function saveLimits(row: AdminKey, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const numberOrNull = (name: string) => {
      const raw = String(form.get(name) ?? "").trim();
      return raw === "" ? null : Number(raw);
    };
    const payload = {
      rpm_limit: numberOrNull("rpm"),
      tpm_limit: numberOrNull("tpm"),
      max_concurrency: numberOrNull("concurrency"),
      budget_limit: String(form.get("budget") ?? "").trim() || null,
    };
    setBusy(true);
    const result = await postJson(`/api/admin/keys/${row.id}/limits`, payload);
    setBusy(false);
    setFlash(resultFlash(result.ok, t.admin.pages.keys.msg.quotaSaved, apiErrorLabel(t, result.envelope, t.admin.pages.keys.msg.quotaFail)));
    if (result.ok) {
      await load();
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.keys.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.keys.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form
        className="flex flex-wrap items-end gap-3 text-sm"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setAppliedQ(q);
          setAppliedStatus(statusFilter);
        }}
      >
        <label>
          {t.admin.pages.keys.email}
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={t.admin.actions.fuzzy}
            className="mt-1 block min-w-56 rounded border border-border bg-transparent px-3 py-2"
          />
        </label>
        <label>
          {t.admin.pages.keys.status}
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="mt-1 block rounded border border-border bg-background px-3 py-2 text-foreground"
          >
            <option value="">{t.labels.common.all}</option>
            <option value="active">{statusLabel(t, "key", "active")}</option>
            <option value="revoked">{statusLabel(t, "key", "revoked")}</option>
          </select>
        </label>
        <button type="submit" className="rounded border border-border px-3 py-2">
          {t.admin.actions.query}
        </button>
      </form>
      {keys.length === 0 && !flash ? <p className="text-sm text-foreground/70">{t.admin.pages.keys.emptyAll}</p> : null}
      <ul className="space-y-4">
        {keys.map((row) => (
          <li key={row.id} className="space-y-3 rounded-lg border border-border p-4 text-sm">
            <p>
              {row.email} · {row.name} · {row.keyPrefix} · {statusLabel(t, "key", row.status)}
            </p>
            <p className="text-xs text-foreground/60">
              {t.console.keys.allowedModels}{" "}
              {row.effectiveModels === null
                ? t.console.keys.allModels
                : row.effectiveModels.join(", ") || t.console.keys.noneModels}
            </p>
            <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => void saveLimits(row, event)}>
              <label>
                {t.admin.pages.keys.rpm}
                <input name="rpm" defaultValue={row.rpm} className="mt-1 block w-28 rounded border border-border bg-transparent px-2 py-1" />
              </label>
              <label>
                {t.admin.pages.keys.tpm}
                <input name="tpm" defaultValue={row.tpm} className="mt-1 block w-28 rounded border border-border bg-transparent px-2 py-1" />
              </label>
              <label>
                {t.admin.pages.keys.concurrency}
                <input name="concurrency" defaultValue={row.concurrency} className="mt-1 block w-24 rounded border border-border bg-transparent px-2 py-1" />
              </label>
              <label>
                {t.admin.pages.keys.budget}
                <input name="budget" defaultValue={row.budget} className="mt-1 block w-32 rounded border border-border bg-transparent px-2 py-1" />
              </label>
              <button type="submit" disabled={busy} className="rounded border border-border px-3 py-1">
                {t.admin.actions.saveQuota}
              </button>
              {row.status === "active" ? (
                <button type="button" disabled={busy} className="rounded border border-border px-3 py-1" onClick={() => void revoke(row)}>
                  {t.admin.actions.revoke}
                </button>
              ) : null}

            </form>
          </li>
        ))}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

function textOrEmpty(value: unknown): string {
  if (typeof value === "number") {
    return String(value);
  }
  return typeof value === "string" ? value : "";
}

function readKeys(value: unknown): AdminKey[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.key_prefix !== "string") {
      return [];
    }
    return [
      {
        id: row.id,
        email: typeof row.email === "string" ? row.email : "",
        name: typeof row.name === "string" ? row.name : "",
        keyPrefix: row.key_prefix,
        status: typeof row.status === "string" ? row.status : "",
        rpm: textOrEmpty(row.rpm_limit),
        tpm: textOrEmpty(row.tpm_limit),
        concurrency: textOrEmpty(row.max_concurrency),
        budget: textOrEmpty(row.budget_limit),
        effectiveModels: Array.isArray(row.effective_models)
          ? row.effective_models.filter((item): item is string => typeof item === "string")
          : null,
      },
    ];
  });
}
