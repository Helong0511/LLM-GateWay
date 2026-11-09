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
import { Field } from "@/components/ui/field";
import { ModelPicker } from "@/components/model-picker";

import { errorMessage, deleteJson, getJson, patchJson, postJson } from "@/lib/api-client";
import { RefreshButton } from "@/components/ui/refresh-button";
import { apiErrorLabel } from "@/lib/error-label";
import { productDisplayName } from "@/lib/product-label";
import { statusLabel } from "@/lib/status-label";

type Product = {
  id: string;
  name: string;
  amount: string;
  bonus_amount: string;
  currency: string;
  enabled: boolean;
  deleted: boolean;
  sort_order: number;
  /** 套餐可用的模型范围；空数组表示不限。 */
  allowed_models: string[];
};

type LifecycleFilter = "enabled" | "disabled" | "deleted" | "all";

async function pullProducts(loadFail: string): Promise<{ items: Product[]; message: string }> {
  const result = await getJson("/api/admin/products");
  if (!result.ok || !result.envelope.data) {
    return { items: [], message: errorMessage(result.envelope, loadFail) };
  }
  return { items: readProducts(result.envelope.data.products), message: "" };
}

function matchesFilter(item: Product, filter: LifecycleFilter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "deleted") {
    return item.deleted;
  }
  if (item.deleted) {
    return false;
  }
  return filter === "enabled" ? item.enabled : !item.enabled;
}

export function AdminProducts() {
  const { t } = useI18n();
  const [products, setProducts] = useState<Product[]>([]);
  const { flash, setFlash } = useBootFlash(t.admin.pages.products.loading);
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [lifecycleFilter, setLifecycleFilter] = useState<LifecycleFilter>("enabled");
  /** 新建套餐时选择包含的模型；空数组表示不限。 */
  const [createModels, setCreateModels] = useState<string[]>([]);
  /** 编辑中的套餐模型草稿。 */
  const [editModels, setEditModels] = useState<string[]>([]);

  async function load() {
    const next = await pullProducts(t.admin.pages.products.loadFail);
    setProducts(next.items);
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullProducts(t.admin.pages.products.loadFail);
      setProducts(next.items);
      setFlash(loadFlash(next.message));
    })();
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    const result = await postJson("/api/admin/products", {
      name: String(form.get("name") || ""),
      amount: String(form.get("amount") || ""),
      bonus_amount: String(form.get("bonus_amount") || "0"),
      sort_order: Number(form.get("sort_order") || 0),
      allowed_models: createModels,
    });
    setBusy(false);
    const m = t.admin.pages.products.msg;
    setFlash(resultFlash(result.ok, m.created, apiErrorLabel(t, result.envelope, m.createFail)));
    if (result.ok) {
      formEl.reset();
      setCreateModels([]);
      await load();
    }
  }

  async function saveEdit(product: Product, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    const result = await patchJson(`/api/admin/products/${product.id}`, {
      name: String(form.get("name") || ""),
      bonus_amount: String(form.get("bonus_amount") || "0"),
      sort_order: Number(form.get("sort_order") || 0),
      enabled: form.get("enabled") === "on",
      allowed_models: editModels,
    });
    setBusy(false);
    const m = t.admin.pages.products.msg;
    setFlash(resultFlash(result.ok, m.updated, apiErrorLabel(t, result.envelope, m.updateFail)));
    if (result.ok) {
      setEditingId("");
      await load();
    }
  }

  async function toggle(product: Product) {
    const nextEnabled = !product.enabled;
    const m = t.admin.pages.products.msg;
    if (!nextEnabled) {
      if (!window.confirm(m.confirmDisable.replace("{name}", product.name))) {
        return;
      }
    }
    setBusy(true);
    const result = await patchJson(`/api/admin/products/${product.id}`, { enabled: nextEnabled });
    setBusy(false);
    setFlash(
      resultFlash(result.ok, nextEnabled ? m.enabled : m.disabled, apiErrorLabel(t, result.envelope, m.updateFail)),
    );
    if (result.ok) {
      if (!nextEnabled) {
        setLifecycleFilter("enabled");
      }
      await load();
    }
  }

  async function remove(product: Product) {
    const m = t.admin.pages.products.msg;
    if (!window.confirm(m.confirmDelete.replace("{name}", product.name))) {
      return;
    }
    setBusy(true);
    const result = await deleteJson(`/api/admin/products/${product.id}`);
    setBusy(false);
    setFlash(resultFlash(result.ok, m.deleted, apiErrorLabel(t, result.envelope, m.deleteFail)));
    if (result.ok) {
      setLifecycleFilter("enabled");
      await load();
    }
  }

  async function restore(product: Product) {
    const m = t.admin.pages.products.msg;
    if (!window.confirm(m.confirmRestore.replace("{name}", product.name))) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/products/${product.id}/restore`, {});
    setBusy(false);
    setFlash(resultFlash(result.ok, m.restored, apiErrorLabel(t, result.envelope, m.restoreFail)));
    if (result.ok) {
      setLifecycleFilter("disabled");
      await load();
    }
  }

  const visible = products.filter((item) => matchesFilter(item, lifecycleFilter));

  return (
    <section className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.products.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.products.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form className="grid max-w-xl gap-3 rounded-md border border-border p-4 text-sm" onSubmit={create}>
        <Field label={t.admin.pages.products.name} hint={t.admin.pages.products.nameHint}>
          <input name="name" required placeholder={t.admin.pages.products.namePlaceholder} className="rounded border border-border bg-transparent px-3 py-2" />
        </Field>
        <Field label={t.admin.pages.products.amount} hint={t.admin.pages.products.amountHint}>
          <input name="amount" required placeholder={t.admin.pages.products.amountPlaceholder} className="rounded border border-border bg-transparent px-3 py-2" />
        </Field>
        <Field label={t.admin.pages.products.bonusAmount} hint={t.admin.pages.products.bonusHint}>
          <input name="bonus_amount" placeholder={t.admin.pages.products.bonusPlaceholder} className="rounded border border-border bg-transparent px-3 py-2" />
        </Field>
        <Field label={t.admin.pages.products.sortOrder} hint={t.admin.pages.products.sortHint}>
          <input name="sort_order" type="number" defaultValue={0} className="rounded border border-border bg-transparent px-3 py-2" />
        </Field>
        <Field label={t.admin.pages.products.models} hint={t.admin.pages.products.modelsHint}>
          <ModelPicker mode="cascade" value={createModels} onChange={setCreateModels} disabled={busy} />
        </Field>
        <button type="submit" disabled={busy} className="w-fit rounded bg-foreground px-4 py-2 text-background">
          {t.admin.actions.createPackage}
        </button>
      </form>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {(["enabled", "disabled", "deleted", "all"] as const).map((value) => {
          const label =
            value === "all"
              ? t.labels.common.all
              : value === "enabled"
                ? t.labels.common.enabled
                : value === "disabled"
                  ? t.labels.common.disabled
                  : statusLabel(t, "provider", "deleted");
          const count = products.filter((item) => matchesFilter(item, value)).length;
          const active = lifecycleFilter === value;
          return (
            <button
              key={value}
              type="button"
              className={
                active
                  ? "rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-accent"
                  : "rounded border border-border px-3 py-1.5 text-foreground/75"
              }
              onClick={() => setLifecycleFilter(value)}
            >
              {label}（{count}）
            </button>
          );
        })}
      </div>
      <ul className="space-y-2 text-sm">
        {visible.length === 0 ? (
          <li className="rounded-lg border border-dashed border-border px-4 py-6 text-foreground/65">
            {lifecycleFilter === "enabled"
              ? t.admin.pages.products.emptyActive
              : lifecycleFilter === "disabled"
                ? t.admin.pages.products.emptyDisabled
                : lifecycleFilter === "deleted"
                  ? t.admin.pages.products.emptyDeleted
                  : t.admin.pages.products.emptyAll}
          </li>
        ) : null}
        {visible.map((item) => (
          <li key={item.id} className="space-y-2 rounded-md border border-border px-3 py-2">
            <div className="flex flex-wrap items-center gap-3">
              <span>
                {productDisplayName(t, item.name)} · {item.amount} {item.currency}
                {item.bonus_amount !== "0.00000000" && item.bonus_amount !== "0"
                  ? ` · ${t.admin.pages.products.bonusPrefix} ${item.bonus_amount}`
                  : ""}{" "}
                ·{" "}
                <span
                  className={
                    item.deleted
                      ? "text-danger"
                      : item.enabled
                        ? "text-[hsl(var(--success-fg))]"
                        : "text-[hsl(var(--warning-fg))]"
                  }
                >
                  {item.deleted
                    ? statusLabel(t, "provider", "deleted")
                    : item.enabled
                      ? t.labels.common.enabled
                      : t.labels.common.disabled}
                </span>
              </span>
              {item.deleted ? (
                <button type="button" disabled={busy} className="rounded border border-border px-3 py-1" onClick={() => void restore(item)}>
                  {t.admin.actions.restore}
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded border border-border px-3 py-1"
                    onClick={() => {
                      if (editingId === item.id) {
                        setEditingId("");
                        setEditModels([]);
                        return;
                      }
                      setEditingId(item.id);
                      setEditModels(item.allowed_models);
                    }}
                  >
                    {editingId === item.id ? t.admin.actions.collapse : t.admin.actions.edit}
                  </button>
                  <button type="button" disabled={busy} className="rounded border border-border px-3 py-1" onClick={() => void toggle(item)}>
                    {item.enabled ? t.admin.actions.disable : t.admin.actions.enable}
                  </button>
                  <button type="button" disabled={busy} className="rounded border border-border px-3 py-1" onClick={() => void remove(item)}>
                    {t.admin.actions.delete}
                  </button>
                </>
              )}
            </div>
            <p className="text-xs text-foreground/60">
              {t.admin.pages.products.models}:{" "}
              {item.allowed_models.length > 0 ? item.allowed_models.join(", ") : t.console.keys.allModels}
            </p>
            {editingId === item.id && !item.deleted ? (
              <form className="grid max-w-xl gap-2 border-t border-border pt-2 sm:grid-cols-2" onSubmit={(event) => void saveEdit(item, event)}>
                <Field label={t.admin.pages.products.name}>
                  <input name="name" required defaultValue={item.name} className="rounded border border-border bg-transparent px-3 py-2" />
                </Field>
                <Field label={t.admin.pages.products.bonusAmount} hint={t.admin.pages.products.editBonusHint}>
                  <input name="bonus_amount" defaultValue={item.bonus_amount} className="rounded border border-border bg-transparent px-3 py-2" />
                </Field>
                <Field label={t.admin.pages.products.sortOrder}>
                  <input name="sort_order" type="number" defaultValue={item.sort_order} className="rounded border border-border bg-transparent px-3 py-2" />
                </Field>
                <label className="flex items-center gap-2 self-end">
                  <input name="enabled" type="checkbox" defaultChecked={item.enabled} />
                  {t.admin.actions.enable}
                </label>
                <div className="sm:col-span-2">
                  <p className="mb-1 text-sm">{t.admin.pages.products.models}</p>
                  <ModelPicker mode="cascade" value={editModels} onChange={setEditModels} disabled={busy} />
                </div>
                <button type="submit" disabled={busy} className="w-fit rounded bg-foreground px-3 py-1.5 text-background">
                  {t.admin.actions.save}
                </button>
              </form>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function readProducts(value: unknown): Product[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.name !== "string" || typeof row.amount !== "string") {
      return [];
    }
    return [
      {
        id: row.id,
        name: row.name,
        amount: row.amount,
        bonus_amount: typeof row.bonus_amount === "string" ? row.bonus_amount : "0",
        currency: typeof row.currency === "string" ? row.currency : "",
        enabled: row.enabled === true,
        deleted: row.deleted === true || typeof row.deleted_at === "string",
        sort_order: typeof row.sort_order === "number" ? row.sort_order : 0,
        allowed_models: Array.isArray(row.allowed_models)
          ? row.allowed_models.filter((value): value is string => typeof value === "string")
          : [],
      },
    ];
  });
}
