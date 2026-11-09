"use client";

import { FormEvent, useEffect, useState } from "react";

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
  type FlashMessage,
} from "@/components/ui/flash";

import { errorMessage, deleteJson, getJson, patchJson, postJson } from "@/lib/api-client";
import { RefreshButton } from "@/components/ui/refresh-button";
import { apiErrorLabel } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

type Credential = { id: string; label: string; hint: string; status: string };
type Provider = {
  id: string;
  name: string;
  kind: string;
  protocol: string;
  base_url: string;
  models_url: string;
  chat_url: string;
  status: string;
  priority: number;
  weight: number;
  last_error: string | null;
  credentials: Credential[];
};
type AllowItem = { id: string; host: string; approved: boolean; note: string };
type Preset = {
  code: string;
  label: string;
  kind: string;
  base_url: string;
  auth: string;
  note: string;
  needs_allowlist: boolean;
};

type PresetCopy = { label: string; note: string };

function presetCopy(
  presets: Record<string, PresetCopy>,
  code: string,
  fallback: { label: string; note: string },
): PresetCopy {
  const hit = presets[code];
  return hit ?? fallback;
}

async function pullProviders(loadFail: string): Promise<{ items: Provider[]; message: string }> {
  const result = await getJson("/api/admin/providers");
  if (!result.ok || !result.envelope.data) {
    return { items: [], message: errorMessage(result.envelope, loadFail) };
  }
  return { items: readProviders(result.envelope.data.providers), message: "" };
}

async function pullAllowlist(): Promise<AllowItem[]> {
  const result = await getJson("/api/admin/allowlist");
  if (!result.ok || !result.envelope.data || !Array.isArray(result.envelope.data.items)) {
    return [];
  }
  return result.envelope.data.items.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.host !== "string") {
      return [];
    }
    return [{ id: row.id, host: row.host, approved: row.approved === true, note: typeof row.note === "string" ? row.note : "" }];
  });
}

async function pullPresets(): Promise<Preset[]> {
  const result = await getJson("/api/admin/providers/presets");
  if (!result.ok || !result.envelope.data || !Array.isArray(result.envelope.data.presets)) {
    return [];
  }
  return result.envelope.data.presets.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.code !== "string" || typeof row.label !== "string" || typeof row.base_url !== "string") {
      return [];
    }
    return [
      {
        code: row.code,
        label: row.label,
        kind: typeof row.kind === "string" ? row.kind : "compatible",
        base_url: row.base_url,
        auth: typeof row.auth === "string" ? row.auth : "bearer",
        note: typeof row.note === "string" ? row.note : "",
        needs_allowlist: row.needs_allowlist === true,
      },
    ];
  });
}

export function AdminProviders() {
  const { t, locale } = useI18n();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [allowlist, setAllowlist] = useState<AllowItem[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [presetCode, setPresetCode] = useState("openai");
  const [name, setName] = useState("OpenAI");
  const [kind, setKind] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [hint, setHint] = useState("");
  const { flash, setFlash } = useBootFlash(t.admin.pages.providers.loading);
  const [busy, setBusy] = useState(false);
  /** 正在执行连通测试的供应商 id；非空时禁止重复发起 */
  const [probingId, setProbingId] = useState("");
  const [editingId, setEditingId] = useState("");
  /** 默认只看启用中。启用 / 停用 / 删除是三种不同状态。 */
  const [statusFilter, setStatusFilter] = useState<"active" | "disabled" | "deleted" | "all">("active");
  const [syncTarget, setSyncTarget] = useState<{ id: string; name: string } | null>(null);
  const [outputMarkup, setOutputMarkup] = useState("10");

  function localizePreset(preset: Preset): PresetCopy {
    const table = t.admin.pages.providers.presets as Record<string, PresetCopy>;
    return presetCopy(table, preset.code, {
      label: preset.label,
      note: preset.note,
    });
  }

  function applyPreset(preset: Preset) {
    const copy = localizePreset(preset);
    setPresetCode(preset.code);
    setName(copy.label);
    setKind(preset.kind);
    setBaseUrl(preset.base_url);
    const allowNote = preset.needs_allowlist ? ` ${t.admin.pages.providers.needsAllowlist}` : "";
    const auth = preset.auth === "x-api-key" ? "x-api-key / Bearer" : "Bearer";
    setHint(`${copy.note}${allowNote} ${t.admin.pages.providers.authPrefix}${auth}.`);
  }

  // 语言切换时：列表标签随 t 重渲染；名称/说明状态同步当前预设文案
  useEffect(() => {
    const current = presets.find((item) => item.code === presetCode);
    if (!current) {
      return;
    }
    const copy = localizePreset(current);
    setName(copy.label);
    const allowNote = current.needs_allowlist ? ` ${t.admin.pages.providers.needsAllowlist}` : "";
    const auth = current.auth === "x-api-key" ? "x-api-key / Bearer" : "Bearer";
    setHint(`${copy.note}${allowNote} ${t.admin.pages.providers.authPrefix}${auth}.`);
  }, [locale, presets, presetCode, t]);

  async function load() {
    const next = await pullProviders(t.admin.pages.providers.loadFail);
    setProviders(next.items);
    setAllowlist(await pullAllowlist());
    const listed = await pullPresets();
    setPresets(listed);
    if (listed.length > 0 && !hint) {
      const first = listed.find((item) => item.code === "openai") ?? listed[0];
      applyPreset(first);
    }
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullProviders(t.admin.pages.providers.loadFail);
      setProviders(next.items);
      setAllowlist(await pullAllowlist());
      const listed = await pullPresets();
      setPresets(listed);
      if (listed.length > 0) {
        const first = listed.find((item) => item.code === "openai") ?? listed[0];
        setPresetCode(first.code);
        setName(first.label);
        setKind(first.kind);
        setBaseUrl(first.base_url);
        const allowNote = first.needs_allowlist ? ` ${t.admin.pages.providers.needsAllowlist}` : "";
        const auth = first.auth === "x-api-key" ? "x-api-key / Bearer" : "Bearer";
        setHint(`${first.note}${allowNote} ${t.admin.pages.providers.authPrefix}${auth}.`);
      }
      setFlash(loadFlash(next.message));
    })();
  }, []);

  async function createProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const result = await postJson("/api/admin/providers", {
      name,
      kind,
      base_url: baseUrl,
    });
    setBusy(false);
    const m = t.admin.pages.providers.msg;
    setFlash(resultFlash(result.ok, m.created, apiErrorLabel(t, result.envelope, m.createFail)));
    if (result.ok) {
      await load();
    }
  }

  async function allowHost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    const result = await postJson("/api/admin/allowlist", {
      host: String(form.get("host") ?? ""),
      note: String(form.get("note") ?? ""),
    });
    setBusy(false);
    const m = t.admin.pages.providers.msg;
    setFlash(resultFlash(result.ok, m.allowApproved, apiErrorLabel(t, result.envelope, m.allowApproveFail)));
    if (result.ok) {
      formEl.reset();
      await load();
    }
  }

  async function revokeAllow(id: string) {
    setBusy(true);
    const result = await postJson(`/api/admin/allowlist/${id}/revoke`, {});
    setBusy(false);
    const m = t.admin.pages.providers.msg;
    setFlash(resultFlash(result.ok, m.allowRevoked, apiErrorLabel(t, result.envelope, m.allowRevokeFail)));
    if (result.ok) {
      await load();
    }
  }

  async function saveSecret(providerId: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    const result = await postJson(`/api/admin/providers/${providerId}/credentials`, {
      label: String(form.get("label") ?? "default"),
      secret: String(form.get("secret") ?? ""),
    });
    setBusy(false);
    const m = t.admin.pages.providers.msg;
    setFlash(resultFlash(result.ok, m.credentialSaved, apiErrorLabel(t, result.envelope, m.credentialSaveFail)));
    if (result.ok) {
      formEl.reset();
      await load();
    }
  }

  async function revokeCredential(id: string) {
    const m = t.admin.pages.providers.msg;
    if (!window.confirm(m.confirmRevokeCredential)) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/credentials/${id}/revoke`, {});
    setBusy(false);
    setFlash(resultFlash(result.ok, m.credentialRevoked, apiErrorLabel(t, result.envelope, m.credentialRevokeFail)));
    if (result.ok) {
      await load();
    }
  }

  async function setStatus(provider: Provider, status: "active" | "disabled") {
    const m = t.admin.pages.providers.msg;
    if (status === "disabled") {
      if (!window.confirm(m.confirmDisable.replace("{name}", provider.name))) {
        return;
      }
    }
    setBusy(true);
    const result = await patchJson(`/api/admin/providers/${provider.id}`, { status });
    setBusy(false);
    setFlash(
      resultFlash(
        result.ok,
        status === "disabled" ? m.disabled : m.enabled,
        apiErrorLabel(t, result.envelope, m.statusFail),
      ),
    );
    if (result.ok) {
      if (status === "disabled") {
        setStatusFilter("active");
      }
      await load();
    }
  }

  async function removeProvider(provider: Provider) {
    const m = t.admin.pages.providers.msg;
    if (!window.confirm(m.confirmDelete.replace("{name}", provider.name))) {
      return;
    }
    setBusy(true);
    const result = await deleteJson(`/api/admin/providers/${provider.id}`);
    setBusy(false);
    setFlash(resultFlash(result.ok, m.deleted, apiErrorLabel(t, result.envelope, m.deleteFail)));
    if (result.ok) {
      setStatusFilter("active");
      await load();
    }
  }

  async function restoreProvider(provider: Provider) {
    const m = t.admin.pages.providers.msg;
    if (!window.confirm(m.confirmRestore.replace("{name}", provider.name))) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/providers/${provider.id}/restore`, {});
    setBusy(false);
    setFlash(resultFlash(result.ok, m.restored, apiErrorLabel(t, result.envelope, m.restoreFail)));
    if (result.ok) {
      setStatusFilter("disabled");
      await load();
    }
  }

  async function saveEdit(provider: Provider, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    const result = await patchJson(`/api/admin/providers/${provider.id}`, {
      name: String(form.get("name") || ""),
      base_url: String(form.get("base_url") || ""),
      priority: Number(form.get("priority") || 0),
      weight: Number(form.get("weight") || 1),
    });
    setBusy(false);
    const m = t.admin.pages.providers.msg;
    setFlash(resultFlash(result.ok, m.updated, apiErrorLabel(t, result.envelope, m.updateFail)));
    if (result.ok) {
      setEditingId("");
      await load();
    }
  }

  async function probe(providerId: string) {
    if (busy || probingId) {
      return; // 避免重复测试
    }
    const m = t.admin.pages.providers.msg;
    setProbingId(providerId);
    setFlash(infoFlash(m.probeRunning)); // 即时反馈：测试已发起
    try {
      const result = await postJson(`/api/admin/providers/${providerId}/probe`, { mode: "connect" });
      if (!result.ok || !result.envelope.data) {
        setFlash(errFlash(apiErrorLabel(t, result.envelope, m.probeFail)));
        return;
      }
      const data = result.envelope.data;
      setFlash(
        data.ok === true
          ? okFlash(m.probeOk.replace("{ms}", String(data.latency_ms)))
          : errFlash(m.probeNg.replace("{error}", String(data.error ?? m.unknownError))),
      );
    } finally {
      setProbingId("");
    }
  }

  function openSyncDialog(provider: Provider) {
    setOutputMarkup("10");
    setSyncTarget({ id: provider.id, name: provider.name });
  }

  function closeSyncDialog() {
    if (busy) {
      return;
    }
    setSyncTarget(null);
  }

  async function confirmSyncModels() {
    if (!syncTarget) {
      return;
    }
    const m = t.admin.pages.providers.msg;
    const markup = Number(outputMarkup);
    if (!Number.isFinite(markup) || markup < 0 || markup > 1000) {
      setFlash(errFlash(m.syncMarkupInvalid));
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/providers/${syncTarget.id}/sync`, {
      output_markup_percent: markup,
    });
    setBusy(false);
    if (!result.ok) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, m.syncFail)));
      return;
    }
    setSyncTarget(null);
    const data = result.envelope.data ?? {};
    setFlash(buildSyncFlash(m, data, markup));
  }

  return (
    <section className="space-y-8">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.providers.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.providers.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-2" onSubmit={createProvider}>
        <div className="text-sm sm:col-span-2">
          <p className="font-medium">{t.admin.pages.providers.officialPresets}</p>
          <p className="mt-0.5 text-xs text-foreground/60">{t.admin.pages.providers.officialPresetsLead}</p>
          {presets.length === 0 ? (
            <p className="mt-2 rounded border border-border bg-background px-3 py-2 text-foreground/60">
              {t.admin.pages.providers.emptyPresets}
            </p>
          ) : (
            <div
              className="mt-2 max-h-56 overflow-y-auto rounded border border-border bg-background"
              role="listbox"
              aria-label={t.admin.pages.providers.officialPresets}
            >
              {presets.map((item) => {
                const active = item.code === presetCode;
                const copy = localizePreset(item);
                return (
                  <button
                    key={item.code}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => applyPreset(item)}
                    className={
                      active
                        ? "flex w-full items-start gap-2 border-b border-border bg-accent/15 px-3 py-2.5 text-left last:border-b-0"
                        : "flex w-full items-start gap-2 border-b border-border px-3 py-2.5 text-left text-foreground/85 last:border-b-0 hover:bg-muted/50"
                    }
                  >
                    <span
                      className={
                        active
                          ? "mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent"
                          : "mt-1.5 h-2 w-2 shrink-0 rounded-full border border-border"
                      }
                      aria-hidden
                    />
                    <span className="min-w-0">
                      <span className="block font-medium text-foreground">{copy.label}</span>
                      <span className="mt-0.5 block truncate font-mono text-xs text-foreground/55">{item.base_url}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          {hint ? <p className="mt-2 text-xs leading-5 text-foreground/65">{hint}</p> : null}
        </div>
        <label className="text-sm">
          {t.admin.pages.providers.displayName}
          <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.displayNameHint}</span>
          <input
            name="name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2"
          />
        </label>
        <label className="text-sm">
          {t.admin.pages.providers.protocolType}
          <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.protocolTypeHint}</span>
          <input name="kind" required value={kind} readOnly className="mt-1 w-full rounded border border-border bg-muted/40 px-3 py-2" />
        </label>
        <label className="text-sm sm:col-span-2">
          {t.admin.pages.providers.baseUrl}
          <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.baseUrlHint}</span>
          <input
            name="base_url"
            required
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="https://api.openai.com/v1"
            className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2 font-mono text-sm"
          />
        </label>
        <button type="submit" disabled={busy} className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground">
          {t.admin.pages.providers.createProvider}
        </button>
      </form>
      <form className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-[1fr_1fr_auto]" onSubmit={allowHost}>
        <label className="text-sm">
          {t.admin.pages.providers.whitelist}
          <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.whitelistHint}</span>
          <input
            name="host"
            required
            placeholder={t.admin.pages.providers.hostPlaceholder}
            className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2"
          />
        </label>
        <label className="text-sm">
          {t.admin.pages.providers.note}
          <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.noteHint}</span>
          <input name="note" className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
        </label>
        <button type="submit" disabled={busy} className="self-end rounded border border-border px-3 py-2 text-sm">
          {t.admin.actions.approve}
        </button>
      </form>
      <div>
        <h2 className="text-lg font-medium">{t.admin.pages.providers.allowlist}</h2>
        <ul className="mt-2 space-y-2 text-sm">
          {allowlist.length === 0 ? (
            <li className="text-foreground/70">{t.admin.pages.providers.emptyAllowlist}</li>
          ) : null}
          {allowlist.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center gap-3">
              <span>
                {item.host} · {item.approved ? t.admin.pages.providers.approved : t.admin.pages.providers.revoked}
                {item.note ? ` · ${item.note}` : ""}
              </span>
              {item.approved ? (
                <button type="button" disabled={busy} className="rounded border border-border px-2 py-1" onClick={() => void revokeAllow(item.id)}>
                  {t.admin.actions.revoke}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {(["active", "disabled", "deleted", "all"] as const).map((value) => {
          const label = value === "all" ? t.labels.common.all : statusLabel(t, "provider", value);
          const count =
            value === "all"
              ? providers.length
              : providers.filter((item) => item.status === value).length;
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
              onClick={() => setStatusFilter(value)}
            >
              {label} ({count})
            </button>
          );
        })}
      </div>
      <ul className="space-y-4">
        {providers.filter((item) => statusFilter === "all" || item.status === statusFilter).length === 0 ? (
          <li className="rounded-lg border border-dashed border-border px-4 py-6 text-sm text-foreground/65">
            {statusFilter === "active"
              ? t.admin.pages.providers.emptyActive
              : statusFilter === "disabled"
                ? t.admin.pages.providers.emptyDisabled
                : statusFilter === "deleted"
                  ? t.admin.pages.providers.emptyDeleted
                  : t.admin.pages.providers.emptyAll}
          </li>
        ) : null}
        {providers
          .filter((item) => statusFilter === "all" || item.status === statusFilter)
          .map((provider) => (
            <li key={provider.id} className="rounded-lg border border-border p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium">
                    {provider.name} · {provider.kind}/{provider.protocol || "openai"} ·{" "}
                    <span
                      className={
                        provider.status === "active"
                          ? "text-[hsl(var(--success-fg))]"
                          : provider.status === "deleted"
                            ? "text-danger"
                            : "text-[hsl(var(--warning-fg))]"
                      }
                    >
                      {statusLabel(t, "provider", provider.status)}
                    </span>
                  </p>
                  <p className="break-all text-sm text-foreground/70">base：{provider.base_url}</p>
                  {provider.models_url ? <p className="break-all text-xs text-foreground/55">models：{provider.models_url}</p> : null}
                  {provider.chat_url ? <p className="break-all text-xs text-foreground/55">chat：{provider.chat_url}</p> : null}
                  {provider.last_error ? <p className="text-sm text-danger">{provider.last_error}</p> : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {provider.status !== "deleted" ? (
                    <>
                      <button type="button" disabled={busy || probingId !== ""} className="rounded border border-border px-3 py-1 text-sm disabled:opacity-60" onClick={() => void probe(provider.id)}>
                        {probingId === provider.id ? t.admin.pages.providers.msg.probeRunning : t.admin.actions.probe}
                      </button>
                      <button type="button" disabled={busy} className="rounded border border-border px-3 py-1 text-sm" onClick={() => openSyncDialog(provider)}>
                        {t.admin.actions.syncModels}
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        className="rounded border border-border px-3 py-1 text-sm"
                        onClick={() => setEditingId(editingId === provider.id ? "" : provider.id)}
                      >
                        {editingId === provider.id ? t.admin.actions.collapse : t.admin.actions.edit}
                      </button>
                      {provider.status === "active" ? (
                        <button type="button" disabled={busy} className="rounded border border-border px-3 py-1 text-sm" onClick={() => void setStatus(provider, "disabled")}>
                          {t.admin.actions.disable}
                        </button>
                      ) : (
                        <button type="button" disabled={busy} className="rounded border border-border px-3 py-1 text-sm" onClick={() => void setStatus(provider, "active")}>
                          {t.admin.actions.enable}
                        </button>
                      )}
                      <button type="button" disabled={busy} className="rounded border border-border px-3 py-1 text-sm" onClick={() => void removeProvider(provider)}>
                        {t.admin.actions.delete}
                      </button>
                    </>
                  ) : (
                    <button type="button" disabled={busy} className="rounded border border-border px-3 py-1 text-sm" onClick={() => void restoreProvider(provider)}>
                      {t.admin.actions.restore}
                    </button>
                  )}
                </div>
              </div>
              {provider.status !== "deleted" && editingId === provider.id ? (
                <form className="mt-3 grid gap-2 border-t border-border pt-3 text-sm sm:grid-cols-2" onSubmit={(event) => void saveEdit(provider, event)}>
                  <label>
                    {t.admin.pages.providers.displayName}
                    <input name="name" required defaultValue={provider.name} className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
                  </label>
                  <label>
                    {t.admin.pages.providers.baseUrl}
                    <input name="base_url" required defaultValue={provider.base_url} className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2 font-mono" />
                  </label>
                  <label>
                    {t.admin.pages.providers.priority}
                    <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.priorityHint}</span>
                    <input name="priority" type="number" defaultValue={provider.priority} className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
                  </label>
                  <label>
                    {t.admin.pages.providers.weight}
                    <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.weightHint}</span>
                    <input name="weight" type="number" min={1} defaultValue={provider.weight} className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
                  </label>
                  <button type="submit" disabled={busy} className="w-fit rounded bg-foreground px-3 py-2 text-background">
                    {t.admin.actions.saveChanges}
                  </button>
                </form>
              ) : null}
              {provider.status !== "deleted" ? (
                <>
                  <ul className="mt-3 space-y-1 text-sm">
                    {provider.credentials.map((item) => (
                      <li key={item.id} className="flex flex-wrap items-center gap-2">
                        <span>
                          {item.label} · {item.hint} ·{" "}
                          {statusLabel(t, "key", item.status === "revoked" ? "revoked" : item.status)}
                        </span>
                        {item.status === "active" ? (
                          <button type="button" disabled={busy} className="rounded border border-border px-2 py-0.5 text-xs" onClick={() => void revokeCredential(item.id)}>
                            {t.admin.actions.revoke}
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(event) => void saveSecret(provider.id, event)}>
                    <label className="text-sm">
                      {t.admin.pages.providers.credentialLabel}
                      <input name="label" defaultValue="default" className="mt-1 block rounded border border-border bg-transparent px-3 py-2 text-sm" />
                    </label>
                    <label className="text-sm">
                      {t.admin.pages.providers.upstreamSecret}
                      <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.providers.upstreamSecretHint}</span>
                      <input
                        name="secret"
                        type="password"
                        required
                        placeholder={t.admin.pages.providers.upstreamSecretPlaceholder}
                        className="mt-1 block rounded border border-border bg-transparent px-3 py-2 text-sm"
                      />
                    </label>
                    <button type="submit" disabled={busy} className="rounded border border-border px-3 py-2 text-sm">
                      {t.admin.pages.providers.saveCredential}
                    </button>
                  </form>
                </>
              ) : null}
            </li>
          ))}
      </ul>
      {syncTarget ? (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="sync-models-title"
          onClick={closeSyncDialog}
        >
          <div
            className="w-full max-w-md rounded-lg border border-border bg-background p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="sync-models-title" className="text-lg font-semibold tracking-tight">
              {t.admin.pages.providers.msg.syncDialogTitle}
            </h2>
            <p className="mt-2 text-sm leading-6 text-foreground/70">
              {t.admin.pages.providers.msg.syncDialogLead}
            </p>
            <p className="mt-2 text-sm text-foreground/80">{syncTarget.name}</p>
            <label className="mt-4 block text-sm">
              {t.admin.pages.providers.msg.syncOutputMarkup}
              <span className="mt-0.5 block text-xs text-foreground/60">
                {t.admin.pages.providers.msg.syncOutputMarkupHint}
              </span>
              <input
                type="number"
                min={0}
                max={1000}
                step="0.1"
                value={outputMarkup}
                onChange={(event) => setOutputMarkup(event.target.value)}
                className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2"
              />
            </label>
            <div className="mt-5 flex flex-wrap justify-end gap-2 text-sm">
              <button
                type="button"
                disabled={busy}
                className="rounded border border-border px-3 py-1.5"
                onClick={closeSyncDialog}
              >
                {t.admin.pages.providers.msg.syncDialogCancel}
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
                onClick={() => void confirmSyncModels()}
              >
                {t.admin.pages.providers.msg.syncDialogConfirm}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

type SyncMsg = {
  synced: string;
  syncedWithPrice: string;
  syncedPriceUp: string;
  syncedPriceDown: string;
  syncedPriceMixed: string;
  syncedPublishedBelow: string;
};

function formatModelSample(names: unknown, total: number): string {
  const list = Array.isArray(names)
    ? names.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
  if (list.length === 0) {
    return "—";
  }
  const joined = list.join("、");
  if (total > list.length) {
    return `${joined}…(+${total - list.length})`;
  }
  return joined;
}

function buildSyncFlash(m: SyncMsg, data: Record<string, unknown>, fallbackMarkup: number): FlashMessage {
  const discovered = Number(data.discovered_count ?? 0);
  const priced = Number(data.priced_count ?? 0);
  const applied = Number(data.output_markup_percent ?? fallbackMarkup);
  const priceNew = Number(data.price_new ?? 0);
  const unchanged = Number(data.price_unchanged ?? 0);
  const increased = Number(data.price_increased ?? 0);
  const decreased = Number(data.price_decreased ?? 0);
  const mixed = Number(data.price_mixed ?? 0);
  const publishedBelow = Number(data.published_below_suggested ?? 0);

  if (priced <= 0) {
    return okFlash(m.synced);
  }

  const parts = [
    m.syncedWithPrice
      .replace("{discovered}", String(discovered))
      .replace("{priced}", String(priced))
      .replace("{markup}", String(applied))
      .replace("{new}", String(priceNew))
      .replace("{unchanged}", String(unchanged)),
  ];
  if (increased > 0) {
    parts.push(
      m.syncedPriceUp
        .replace("{count}", String(increased))
        .replace("{names}", formatModelSample(data.price_increased_models, increased)),
    );
  }
  if (decreased > 0) {
    parts.push(
      m.syncedPriceDown
        .replace("{count}", String(decreased))
        .replace("{names}", formatModelSample(data.price_decreased_models, decreased)),
    );
  }
  if (mixed > 0) {
    parts.push(
      m.syncedPriceMixed
        .replace("{count}", String(mixed))
        .replace("{names}", formatModelSample(data.price_mixed_models, mixed)),
    );
  }
  if (publishedBelow > 0) {
    parts.push(
      m.syncedPublishedBelow
        .replace("{count}", String(publishedBelow))
        .replace("{names}", formatModelSample(data.published_below_models, publishedBelow)),
    );
  }
  const text = parts.join(" ");
  return increased > 0 || publishedBelow > 0 ? warnFlash(text) : okFlash(text);
}

function readProviders(value: unknown): Provider[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.name !== "string" || typeof row.base_url !== "string") {
      return [];
    }
    const credentials = Array.isArray(row.credentials)
      ? row.credentials.flatMap((entry) => {
        if (!entry || typeof entry !== "object") {
          return [];
        }
        const credential = entry as Record<string, unknown>;
        if (typeof credential.id !== "string" || typeof credential.hint !== "string") {
          return [];
        }
        return [
          {
            id: credential.id,
            label: typeof credential.label === "string" ? credential.label : "",
            hint: credential.hint,
            status: typeof credential.status === "string" ? credential.status : "",
          },
        ];
      })
      : [];
    return [
      {
        id: row.id,
        name: row.name,
        kind: typeof row.kind === "string" ? row.kind : "",
        protocol: typeof row.protocol === "string" ? row.protocol : "",
        base_url: row.base_url,
        models_url: typeof row.models_url === "string" ? row.models_url : "",
        chat_url: typeof row.chat_url === "string" ? row.chat_url : "",
        status: typeof row.status === "string" ? row.status : "",
        priority: typeof row.priority === "number" ? row.priority : 100,
        weight: typeof row.weight === "number" ? row.weight : 1,
        last_error: typeof row.last_error === "string" ? row.last_error : null,
        credentials,
      },
    ];
  });
}
