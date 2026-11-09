"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
  loadFlash,
  resultFlash,
  warnFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { Button } from "@/components/ui/button";
import { errorMessage, deleteJson, getJson, patchJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

type ApiKeyRow = {
  id: string;
  name: string;
  keyPrefix: string;
  /** 列表展示用的掩码：sk-abc123******************** */
  maskedSecret: string;
  /** 是否能通过二次验证取回明文（存量密钥可能无法）。 */
  revealable: boolean;
  status: string;
  budgetLimit: string | null;
  budgetSpent: string | null;
  rpmLimit: string;
  tpmLimit: string;
  maxConcurrency: string;
  /** 账号级有效模型；null 表示不限（继承套餐或全部已上架）。 */
  effectiveModels: string[] | null;
  createdAt: string;
};

function textOrEmpty(value: unknown): string {
  if (typeof value === "number") {
    return String(value);
  }
  return typeof value === "string" ? value : "";
}

function asKey(value: unknown): ApiKeyRow | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  if (typeof row.id !== "string" || typeof row.name !== "string" || typeof row.key_prefix !== "string") {
    return null;
  }
  return {
    id: row.id,
    name: row.name,
    keyPrefix: row.key_prefix,
    maskedSecret: typeof row.masked_secret === "string" ? row.masked_secret : row.key_prefix + "*".repeat(20),
    revealable: row.revealable === true,
    status: typeof row.status === "string" ? row.status : "",
    budgetLimit: typeof row.budget_limit === "string" ? row.budget_limit : null,
    budgetSpent: typeof row.budget_spent === "string" ? row.budget_spent : null,
    rpmLimit: textOrEmpty(row.rpm_limit),
    tpmLimit: textOrEmpty(row.tpm_limit),
    maxConcurrency: textOrEmpty(row.max_concurrency),
    effectiveModels: Array.isArray(row.effective_models)
      ? row.effective_models.filter((item): item is string => typeof item === "string")
      : null,
    createdAt: typeof row.created_at === "string" ? row.created_at : "",
  };
}

async function pullKeys(loadFail: string): Promise<{ keys: ApiKeyRow[]; message: string }> {
  const result = await getJson("/api/keys");
  if (!result.ok || !Array.isArray(result.envelope.data?.keys)) {
    return { keys: [], message: errorMessage(result.envelope, loadFail) };
  }
  return {
    keys: result.envelope.data.keys.map(asKey).filter((item): item is ApiKeyRow => item !== null),
    message: "",
  };
}

export function KeysPanel() {
  const { t } = useI18n();
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [name, setName] = useState("");
  const [budget, setBudget] = useState("");
  /** 刚创建的密钥明文，仅用于一次性复制，复制后立即清空，绝不注入 DOM 持久化。 */
  const [freshSecret, setFreshSecret] = useState("");
  const [freshName, setFreshName] = useState("");
  const { flash, setFlash } = useBootFlash(t.console.keys.loading);
  const [copied, setCopied] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState("");
  /** 等待密码验证的密钥；空字符串表示弹窗关闭。 */
  const [revealTarget, setRevealTarget] = useState<ApiKeyRow | null>(null);
  const [revealPassword, setRevealPassword] = useState("");
  const [revealBusy, setRevealBusy] = useState(false);
  const [revealError, setRevealError] = useState("");
  /** 启用 / 停用 / 删除(吊销) 三态；默认启用中。 */
  const [statusFilter, setStatusFilter] = useState<"active" | "disabled" | "revoked" | "all">("active");
  const baseUrl = useMemo(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return `${window.location.origin}/v1`;
  }, []);

  async function load() {
    const next = await pullKeys(t.console.keys.loadFail);
    setKeys(next.keys);
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullKeys(t.console.keys.loadFail);
      setKeys(next.keys);
      setFlash(loadFlash(next.message));
    })();
  }, []);

  async function createKey(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await postJson("/api/keys", {
      name,
      budget_limit: budget.trim() || null,
    });
    setBusy(false);
    if (!result.ok || typeof result.envelope.data?.secret !== "string") {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.keys.msg.createFail)));
      return;
    }
    const data = result.envelope.data as { secret?: string; name?: string };
    if (typeof data.secret !== "string") {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.keys.msg.createFail)));
      return;
    }
    setFreshSecret(data.secret);
    setFreshName(typeof data.name === "string" ? data.name : name);
    // 故意不在 DOM 上渲染明文；只通过剪贴板 API 交付给用户。
    void copyToClipboard(`fresh-${data.secret.slice(-8)}`, data.secret, false);
    setFlash(warnFlash(t.console.keys.msg.secretOnce));
    setName("");
    setBudget("");
    await load();
  }

  async function setKeyStatus(item: ApiKeyRow, status: "active" | "disabled") {
    if (status === "disabled") {
      const ok = window.confirm(t.console.keys.msg.confirmDisable.replace("{name}", item.name));
      if (!ok) {
        return;
      }
    }
    setBusy(true);
    const result = await patchJson(`/api/keys/${item.id}`, { status });
    setBusy(false);
    setFlash(
      resultFlash(
        result.ok,
        status === "disabled" ? t.console.keys.msg.disabled : t.console.keys.msg.enabled,
        apiErrorLabel(t, result.envelope, t.console.keys.msg.statusFail),
      ),
    );
    if (result.ok) {
      if (status === "disabled") {
        setStatusFilter("active");
      }
      await load();
    }
  }

  async function removeKey(item: ApiKeyRow) {
    if (!window.confirm(t.console.keys.msg.confirmDelete.replace("{name}", item.name))) {
      return;
    }
    setBusy(true);
    const result = await deleteJson(`/api/keys/${item.id}`);
    setBusy(false);
    setFlash(
      resultFlash(
        result.ok,
        t.console.keys.msg.deleted,
        apiErrorLabel(t, result.envelope, t.console.keys.msg.deleteFail),
      ),
    );
    if (result.ok) {
      if (editingId === item.id) {
        setEditingId("");
      }
      setStatusFilter("active");
      await load();
    }
  }

  async function saveEdit(item: ApiKeyRow, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nextName = String(form.get("name") || "").trim();
    const nextBudget = String(form.get("budget") || "").trim();
    const rpm = String(form.get("rpm") || "").trim();
    const tpm = String(form.get("tpm") || "").trim();
    const concurrency = String(form.get("concurrency") || "").trim();
    if (!nextName) {
      setFlash(warnFlash(t.console.keys.msg.nameRequired));
      return;
    }
    setBusy(true);
    const result = await patchJson(`/api/keys/${item.id}`, {
      name: nextName,
      budget_limit: nextBudget || null,
      clear_budget_limit: nextBudget === "",
      rpm_limit: rpm ? Number(rpm) : null,
      clear_rpm_limit: rpm === "",
      tpm_limit: tpm ? Number(tpm) : null,
      clear_tpm_limit: tpm === "",
      max_concurrency: concurrency ? Number(concurrency) : null,
      clear_max_concurrency: concurrency === "",
    });
    setBusy(false);
    setFlash(
      resultFlash(result.ok, t.console.keys.msg.updated, apiErrorLabel(t, result.envelope, t.console.keys.msg.updateFail)),
    );
    if (result.ok) {
      setEditingId("");
      await load();
    }
  }

  async function copyToClipboard(label: string, value: string, persistState = true) {
    let ok = false;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        ok = true;
      }
    } catch {
      ok = false;
    }
    if (!ok && typeof document !== "undefined") {
      // 降级：创建离屏 textarea 并用 execCommand（兼容旧浏览器/非安全上下文）。
      try {
        const ta = document.createElement("textarea");
        ta.value = value;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        ta.setSelectionRange(0, value.length);
        ok = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch {
        ok = false;
      }
    }
    if (ok) {
      setCopied(label);
      if (persistState) {
        window.setTimeout(() => setCopied((cur) => (cur === label ? "" : cur)), 2000);
      }
      return true;
    }
    setFlash(warnFlash(t.console.keys.msg.copyFail));
    return false;
  }

  async function confirmRevealAndCopy(item: ApiKeyRow) {
    setRevealBusy(true);
    setRevealError("");
    const result = await postJson(`/api/keys/${item.id}/reveal`, { password: revealPassword });
    setRevealBusy(false);
    if (!result.ok || typeof result.envelope.data?.secret !== "string") {
      setRevealError(apiErrorLabel(t, result.envelope, t.console.keys.msg.revealFail));
      return;
    }
    const secret = result.envelope.data.secret;
    const copiedOk = await copyToClipboard(`reveal-${item.id}`, secret, false);
    // 立即清空 state，不留任何痕迹。
    setRevealPassword("");
    setRevealTarget(null);
    if (copiedOk) {
      setFlash(resultFlash(true, t.console.keys.msg.revealCopied, ""));
    }
  }

  const k = t.console.keys;
  const ak = t.admin.pages.keys;
  const actions = t.admin.actions;

  function emptyMessage(): string {
    if (statusFilter === "active") {
      return keys.length === 0 ? k.emptyFresh : k.emptyActiveFiltered;
    }
    if (statusFilter === "disabled") {
      return ak.emptyDisabled;
    }
    if (statusFilter === "revoked") {
      return ak.emptyDeleted;
    }
    return ak.emptyAll;
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{k.title}</h1>
        <p className="mt-2 text-sm text-foreground/70">{k.lead}</p>
      </header>

      <div className="tech-panel flex flex-wrap items-center gap-3 rounded-lg px-4 py-3 text-sm">
        <div>
          <p className="text-xs text-accent">{k.baseUrl}</p>
          <p className="mt-1 font-mono text-sm">{baseUrl || "/v1"}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void copyToClipboard("url", baseUrl || "/v1")}>
          {copied === "url" ? k.copied : k.copyUrl}
        </Button>
      </div>

      {flash ? <FlashBanner flash={flash} compact className="mt-0" /> : null}
      {freshSecret ? (
        <div className="space-y-2 rounded-md border border-border bg-muted px-3 py-3 text-sm">
          <p className="font-medium">{k.msg.keyCreated.replace("{name}", freshName || "")}</p>
          <p className="text-xs text-foreground/70">{k.msg.secretOnce}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" onClick={() => void copyToClipboard(`fresh-copy-${copied}`, freshSecret)}>
              {copied.startsWith("fresh-copy") ? k.copied : k.copySecret}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setFreshSecret("")}>
              {k.msg.secretDismissed}
            </Button>
          </div>
        </div>
      ) : null}

      <form className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-2" onSubmit={(event) => void createKey(event)}>
        <label className="block text-sm sm:col-span-2">
          {k.keyName}
          <span className="mt-0.5 block text-xs text-foreground/60">{k.keyNameHint}</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2"
            placeholder={k.keyNamePlaceholder}
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </label>
        <p className="block text-sm text-foreground/70 sm:col-span-2">{k.allowedModelsInherited}</p>
        <label className="block text-sm">
          {k.budgetLimit}
          <span className="mt-0.5 block text-xs text-foreground/60">{k.budgetHint}</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2"
            placeholder={k.budgetPlaceholder}
            inputMode="decimal"
            value={budget}
            onChange={(event) => setBudget(event.target.value)}
          />
        </label>
        <div className="flex items-end">
          <Button type="submit" disabled={busy}>
            {k.createKey}
          </Button>
        </div>
      </form>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {(["active", "disabled", "revoked", "all"] as const).map((value) => {
          const label = value === "all" ? t.labels.common.all : statusLabel(t, "key", value);
          const count =
            value === "all" ? keys.length : keys.filter((item) => item.status === value).length;
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
              {label}（{count}）
            </button>
          );
        })}
      </div>

      {keys.filter((item) => statusFilter === "all" || item.status === statusFilter).length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-foreground/70">
          {emptyMessage()}
        </p>
      ) : null}

      <ul className="space-y-3">
        {keys
          .filter((item) => statusFilter === "all" || item.status === statusFilter)
          .map((item) => (
            <li key={item.id} className="rounded-lg border border-border p-4 text-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <p className="font-medium">
                    {item.name} ·{" "}
                    <span
                      className={
                        item.status === "active"
                          ? "text-[hsl(var(--success-fg))]"
                          : item.status === "revoked"
                            ? "text-danger"
                            : "text-[hsl(var(--warning-fg))]"
                      }
                    >
                      {statusLabel(t, "key", item.status)}
                    </span>
                  </p>
                  <p className="font-mono text-xs text-foreground/70">{item.maskedSecret}</p>
                  {item.revealable ? (
                    <button
                      type="button"
                      className="text-xs text-accent hover:underline disabled:cursor-not-allowed disabled:text-foreground/40"
                      disabled={busy}
                      onClick={() => {
                        setRevealTarget(item);
                        setRevealPassword("");
                        setRevealError("");
                      }}
                    >
                      {k.msg.revealAction}
                    </button>
                  ) : (
                    <p className="text-xs text-foreground/45">{k.msg.revealUnavailable}</p>
                  )}
                  <p className="text-foreground/70">
                    {k.budgetLabel} {item.budgetLimit ?? k.unlimited} · {k.spent} {item.budgetSpent ?? "0"} ·{" "}
                    {t.shell.consoleNav.models}{" "}
                    {item.effectiveModels === null
                      ? k.allModels
                      : item.effectiveModels.join("、") || k.noneModels}
                  </p>
                  <p className="text-xs text-foreground/55">
                    RPM {item.rpmLimit || k.noLimit} · TPM {item.tpmLimit || k.noLimit} · {ak.concurrency}{" "}
                    {item.maxConcurrency || k.noLimit} · {item.createdAt || actions.none}
                  </p>
                </div>
                {item.status === "active" || item.status === "disabled" ? (
                  <div className="flex flex-wrap gap-2">
                    {item.status === "active" ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() => setEditingId(editingId === item.id ? "" : item.id)}
                      >
                        {editingId === item.id ? k.collapse : k.edit}
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => void setKeyStatus(item, item.status === "active" ? "disabled" : "active")}
                    >
                      {item.status === "active" ? actions.disable : actions.enable}
                    </Button>
                    <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void removeKey(item)}>
                      {actions.delete}
                    </Button>
                  </div>
                ) : null}
              </div>
              {editingId === item.id && item.status === "active" ? (
                <form className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-2" onSubmit={(event) => void saveEdit(item, event)}>
                  <label className="sm:col-span-2">
                    {k.name}
                    <input name="name" required defaultValue={item.name} className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2" />
                  </label>
                  <p className="text-sm text-foreground/70 sm:col-span-2">{k.allowedModelsEdit}</p>
                  <label>
                    {k.budgetCap}
                    <input name="budget" defaultValue={item.budgetLimit ?? ""} placeholder={k.budgetPlaceholder} className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2" />
                  </label>
                  <label>
                    {ak.rpm}
                    <input name="rpm" defaultValue={item.rpmLimit} placeholder={k.budgetPlaceholder} className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2" />
                  </label>
                  <label>
                    {ak.tpm}
                    <input name="tpm" defaultValue={item.tpmLimit} placeholder={k.budgetPlaceholder} className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2" />
                  </label>
                  <label>
                    {ak.concurrency}
                    <input name="concurrency" defaultValue={item.maxConcurrency} placeholder={k.budgetPlaceholder} className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2" />
                  </label>
                  <div className="flex gap-2 sm:col-span-2">
                    <Button type="submit" disabled={busy}>
                      {k.saveEdit}
                    </Button>
                    <Button type="button" variant="outline" disabled={busy} onClick={() => setEditingId("")}>
                      {actions.cancel}
                    </Button>
                  </div>
                </form>
              ) : null}
            </li>
          ))}
      </ul>

      {revealTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-8">
          <div className="w-full max-w-md rounded-lg border border-border bg-background p-5 text-sm shadow-xl">
            <h2 className="text-base font-semibold">{k.msg.revealTitle}</h2>
            <p className="mt-1 text-foreground/70">
              {k.msg.revealBody.replace("{name}", revealTarget.name)}
            </p>
            <form
              className="mt-4 space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void confirmRevealAndCopy(revealTarget);
              }}
            >
              <label className="block">
                {k.msg.revealPasswordLabel}
                <input
                  type="password"
                  autoFocus
                  autoComplete="current-password"
                  value={revealPassword}
                  onChange={(event) => setRevealPassword(event.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2"
                  required
                  minLength={6}
                  disabled={revealBusy}
                />
              </label>
              {revealError ? <p className="text-danger">{revealError}</p> : null}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={revealBusy}
                  onClick={() => {
                    setRevealTarget(null);
                    setRevealPassword("");
                    setRevealError("");
                  }}
                >
                  {actions.cancel}
                </Button>
                <Button type="submit" disabled={revealBusy || !revealPassword}>
                  {revealBusy ? k.msg.revealWorking : k.msg.revealConfirm}
                </Button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}
