"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
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
import { Field } from "@/components/ui/field";
import { RefreshButton } from "@/components/ui/refresh-button";

import { PageControls } from "@/components/page-controls";
import type { Messages } from "@/content/messages";
import { deleteJson, getJson, patchJson, postJson } from "@/lib/api-client";
import { apiErrorLabel, COUPON_WARN_CODES } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

const PAGE_SIZE = 20;

type Row = Record<string, unknown>;

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function withPage(path: string, page: number): string {
  const join = path.includes("?") ? "&" : "?";
  return `${path}${join}page=${page}&page_size=${PAGE_SIZE}`;
}

async function pull(
  path: string,
  loadFail: string,
  t: Messages,
): Promise<{ data: Row | null; message: string }> {
  const result = await getJson(path);
  if (!result.ok || !result.envelope.data) {
    return { data: null, message: apiErrorLabel(t, result.envelope, loadFail) };
  }
  return { data: result.envelope.data, message: "" };
}

function useData(path: string, loadFail?: string) {
  const { t } = useI18n();
  const fail = loadFail ?? t.admin.actions.loadFail;
  const [data, setData] = useState<Row | null>(null);
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    void (async () => {
      const next = await pull(withPage(path, page), fail, t);
      setData(next.data);
      setFlash(loadFlash(next.message));
    })();
  }, [path, page, version, fail, t]);

  return {
    data,
    flash,
    setFlash,
    page,
    setPage,
    total: typeof data?.total === "number" ? data.total : 0,
    reload: () => setVersion((value) => value + 1),
  };
}

const TICKET_CATEGORY_KEYS = ["billing", "technical", "refund", "chain", "other"] as const;

export function TicketPanel({ admin = false }: { admin?: boolean }) {
  const { t } = useI18n();
  const path = admin ? "/api/admin/tickets" : "/api/tickets";
  const { data, flash, setFlash, page, setPage, total, reload } = useData(path);
  const tickets = Array.isArray(data?.tickets) ? (data.tickets as Row[]) : [];
  const [openId, setOpenId] = useState("");
  const [detail, setDetail] = useState<Row | null>(null);
  const categoryLabel = (key: string) =>
    t.labels.ticketCategory[key as keyof typeof t.labels.ticketCategory] || key;

  async function createTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const result = await postJson("/api/tickets", {
      category: String(form.get("category") || "billing"),
      subject: String(form.get("subject") || ""),
      body: String(form.get("body") || ""),
    });
    setFlash(resultFlash(result.ok, t.admin.pages.tickets.msg.submitted, apiErrorLabel(t, result.envelope, t.admin.pages.tickets.msg.submitFail)));
    if (result.ok) {
      formEl.reset();
      reload();
    }
  }

  async function openTicket(id: string) {
    setOpenId(id);
    const result = await getJson(admin ? `/api/admin/tickets/${id}` : `/api/tickets/${id}`);
    setDetail(result.ok ? result.envelope.data ?? null : null);
    if (!result.ok) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.tickets.msg.notFound)));
    }
  }

  async function reply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!openId) {
      return;
    }
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const target = admin ? `/api/admin/tickets/${openId}/messages` : `/api/tickets/${openId}/messages`;
    const result = await postJson(target, {
      body: String(form.get("body") || ""),
      status: admin ? String(form.get("status") || "pending") : undefined,
    });
    setFlash(resultFlash(result.ok, t.admin.pages.tickets.msg.replySaved, apiErrorLabel(t, result.envelope, t.admin.pages.tickets.msg.replyFail)));
    if (result.ok) {
      formEl.reset();
      setDetail(result.envelope.data ?? null);
      reload();
    }
  }

  async function closeTicket(id: string) {
    const path = admin ? `/api/admin/tickets/${id}/close` : `/api/tickets/${id}/close`;
    const result = await postJson(path, {});
    setFlash(resultFlash(result.ok, t.admin.pages.tickets.msg.closed, apiErrorLabel(t, result.envelope, t.admin.pages.tickets.msg.closeFail)));
    if (result.ok) {
      reload();
      if (openId === id) {
        setDetail(null);
        setOpenId("");
      }
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">
              {admin ? t.admin.pages.tickets.title : t.console.tickets.title}
            </h1>
            <p className="mt-3 text-sm text-foreground/70">
              {admin ? t.admin.pages.tickets.lead : t.console.tickets.lead}
            </p>
          </div>
          {admin ? <RefreshButton onRefresh={reload} /> : null}
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
        {!flash && !data ? <p className="mt-3 text-sm text-foreground/70">{t.admin.actions.loading}</p> : null}
      </div>
      {admin ? null : (
        <form onSubmit={createTicket} className="grid max-w-xl gap-3 text-sm">
          <Field label={t.admin.pages.tickets.category} hint={t.admin.pages.tickets.categoryHint}>
            <select name="category" className="rounded border border-border bg-background px-3 py-2 text-foreground">
              {TICKET_CATEGORY_KEYS.map((value) => (
                <option key={value} value={value}>
                  {categoryLabel(value)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t.admin.pages.tickets.subject} hint={t.admin.pages.tickets.subjectHint}>
            <input
              name="subject"
              required
              placeholder={t.admin.pages.tickets.subjectPlaceholder}
              className="rounded border border-border bg-background px-3 py-2"
            />
          </Field>
          <Field label={t.admin.pages.tickets.body} hint={t.admin.pages.tickets.bodyHint}>
            <textarea
              name="body"
              required
              placeholder={t.admin.pages.tickets.bodyPlaceholder}
              className="min-h-24 rounded border border-border bg-background px-3 py-2"
            />
          </Field>
          <button className="w-fit rounded bg-foreground px-4 py-2 text-background" type="submit">
            {t.admin.pages.tickets.submit}
          </button>
        </form>
      )}
      <ul className="space-y-2 text-sm">
        {tickets.length === 0 ? <li>{t.admin.pages.tickets.empty}</li> : null}
        {tickets.map((item) => (
          <li key={text(item.id)} className="flex flex-wrap items-center gap-3">
            <button type="button" className="text-left" onClick={() => void openTicket(text(item.id))}>
              {text(item.subject)} · {categoryLabel(text(item.category))} ·{" "}
              {statusLabel(t, "ticket", text(item.status))}
              {admin ? ` · ${text(item.email)}` : ""}
            </button>
            {item.status !== "closed" ? (
              <button type="button" className="rounded border border-border px-2 py-1 text-xs" onClick={() => void closeTicket(text(item.id))}>
                {t.admin.actions.close}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
      {detail ? (
        <form onSubmit={reply} className="grid max-w-xl gap-3 text-sm">
          {Array.isArray(detail.messages)
            ? (detail.messages as Row[]).map((item) => (
              <p key={text(item.id)} className="rounded border border-border p-3">
                {text(item.body)}
              </p>
            ))
            : null}
          <Field label={t.admin.pages.tickets.reply}>
            <textarea
              name="body"
              required
              placeholder={t.admin.pages.tickets.replyPlaceholder}
              className="min-h-20 rounded border border-border bg-background px-3 py-2"
            />
          </Field>
          {admin ? (
            <Field label={t.admin.pages.tickets.ticketStatus} hint={t.admin.pages.tickets.ticketStatusHint}>
              <select name="status" defaultValue={text(detail.status)} className="rounded border border-border bg-background px-3 py-2 text-foreground">
                {(["open", "pending", "resolved", "closed"] as const).map((value) => (
                  <option key={value} value={value}>
                    {statusLabel(t, "ticket", value)}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
          <button className="w-fit rounded bg-foreground px-4 py-2 text-background" type="submit">
            {t.admin.pages.tickets.sendReply}
          </button>
        </form>
      ) : null}
    </section>
  );
}

export function InvoicePanel({ admin = false }: { admin?: boolean }) {
  const { t } = useI18n();
  const { data, flash, setFlash, page, setPage, total, reload } = useData(admin ? "/api/admin/invoices" : "/api/invoices");
  const invoices = Array.isArray(data?.invoices) ? (data.invoices as Row[]) : [];

  async function requestInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const result = await postJson("/api/invoices", {
      order_no: String(form.get("order_no") || ""),
      title: String(form.get("title") || ""),
      tax_no: String(form.get("tax_no") || ""),
    });
    setFlash(resultFlash(result.ok, t.admin.pages.invoices.msg.submitted, apiErrorLabel(t, result.envelope, t.admin.pages.invoices.msg.submitFail)));
    if (result.ok) {
      formEl.reset();
      reload();
    }
  }

  async function review(id: string, status: "issued" | "rejected") {
    const result = await postJson(`/api/admin/invoices/${id}/status`, { status });
    setFlash(resultFlash(result.ok, t.admin.pages.invoices.msg.updated, apiErrorLabel(t, result.envelope, t.admin.pages.invoices.msg.updateFail)));
    if (result.ok) {
      reload();
    }
  }

  async function cancelInvoice(id: string) {
    const result = await postJson(`/api/invoices/${id}/cancel`, {});
    setFlash(resultFlash(result.ok, t.admin.pages.invoices.msg.cancelled, apiErrorLabel(t, result.envelope, t.admin.pages.invoices.msg.cancelFail)));
    if (result.ok) {
      reload();
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">
              {admin ? t.admin.pages.invoices.title : t.console.invoices.title}
            </h1>
            <p className="mt-3 text-sm text-foreground/70">
              {admin ? t.admin.pages.invoices.lead : t.console.invoices.lead}
            </p>
          </div>
          {admin ? <RefreshButton onRefresh={reload} /> : null}
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      {admin ? null : (
        <form onSubmit={requestInvoice} className="grid max-w-xl gap-3 text-sm">
          <Field label={t.admin.pages.invoices.orderNo} hint={t.admin.pages.invoices.orderNoHint}>
            <input
              name="order_no"
              required
              placeholder={t.admin.pages.invoices.orderNoPlaceholder}
              className="rounded border border-border bg-background px-3 py-2"
            />
          </Field>
          <Field label={t.admin.pages.invoices.invoiceTitle} hint={t.admin.pages.invoices.invoiceTitleHint}>
            <input
              name="title"
              required
              placeholder={t.admin.pages.invoices.invoiceTitlePlaceholder}
              className="rounded border border-border bg-background px-3 py-2"
            />
          </Field>
          <Field label={t.admin.pages.invoices.taxNo} hint={t.admin.pages.invoices.taxNoHint}>
            <input
              name="tax_no"
              placeholder={t.admin.pages.invoices.taxNoPlaceholder}
              className="rounded border border-border bg-background px-3 py-2"
            />
          </Field>
          <button className="w-fit rounded bg-foreground px-4 py-2 text-background" type="submit">
            {t.admin.pages.invoices.submit}
          </button>
        </form>
      )}
      <ul className="space-y-2 text-sm">
        {invoices.length === 0 ? <li>{t.admin.pages.invoices.empty}</li> : null}
        {invoices.map((item) => (
          <li key={text(item.id)} className="flex flex-wrap items-center gap-3 border-b border-border py-2">
            <span>
              {text(item.order_no)} · {text(item.title)} · {text(item.amount)} {text(item.currency)} ·{" "}
              {statusLabel(t, "invoice", text(item.status))}
              {admin ? ` · ${text(item.email)}` : ""}
            </span>
            {admin && data?.can_review === true && item.status === "requested" ? (
              <>
                <button type="button" onClick={() => void review(text(item.id), "issued")}>
                  {t.admin.actions.issue}
                </button>
                <button type="button" onClick={() => void review(text(item.id), "rejected")}>
                  {t.admin.actions.reject}
                </button>
              </>
            ) : null}
            {!admin && item.status === "requested" ? (
              <button type="button" onClick={() => void cancelInvoice(text(item.id))}>
                {t.admin.actions.revoke}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

export function CouponRedeem() {
  const { t } = useI18n();
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [redemptions, setRedemptions] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);

  async function loadRedemptions() {
    const result = await getJson("/api/coupons/redemptions");
    if (!result.ok || !Array.isArray(result.envelope.data?.redemptions)) {
      setFlash(warnFlash(apiErrorLabel(t, result.envelope, t.console.coupons.msg.loadRedemptionsFail)));
      setRedemptions([]);
      return;
    }
    setRedemptions(result.envelope.data.redemptions as Row[]);
  }

  useEffect(() => {
    void loadRedemptions();
  }, []);

  async function redeem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const code = String(form.get("code") || "").trim();
    if (!code) {
      setFlash(warnFlash(t.console.coupons.msg.codeRequired));
      return;
    }
    setBusy(true);
    const result = await postJson("/api/coupons/redeem", { code });
    setBusy(false);
    if (!result.ok || !result.envelope.data) {
      const codeKey = (result.envelope.error?.code || "").trim();
      const text = apiErrorLabel(t, result.envelope, t.console.coupons.msg.redeemFail);
      setFlash(COUPON_WARN_CODES.has(codeKey) ? warnFlash(text) : errFlash(text));
      return;
    }
    formEl.reset();
    const data = result.envelope.data;
    const shown = text(data.formatted) || text(data.code);
    setFlash(okFlash(t.console.coupons.msg.redeemOk.replace("{code}", shown).replace("{amount}", text(data.bonus_amount)).replace("{currency}", text(data.currency))));
    await loadRedemptions();
  }

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{t.console.coupons.title}</h1>
        <p className="mt-3 text-sm text-foreground/70">{t.console.coupons.lead}</p>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form onSubmit={redeem} className="grid max-w-xl gap-3 text-sm">
        <Field label={t.console.coupons.code} hint={t.console.coupons.codeHint}>
          <input
            name="code"
            required
            disabled={busy}
            placeholder={t.console.coupons.codePlaceholder}
            className="w-full rounded border border-border bg-background px-3 py-2 font-mono"
            autoComplete="off"
            spellCheck={false}
          />
        </Field>
        <button className="w-fit rounded bg-foreground px-4 py-2 text-background disabled:opacity-60" type="submit" disabled={busy}>
          {busy ? t.admin.actions.redeeming : t.admin.actions.redeem}
        </button>
      </form>
      <ul className="space-y-2 text-sm">
        {redemptions.length === 0 ? <li className="text-foreground/70">{t.console.coupons.empty}</li> : null}
        {redemptions.map((item) => (
          <li key={text(item.id)}>
            {text(item.code)} · {text(item.bonus_amount)} {text(item.currency)} · {text(item.created_at)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function couponStatusClass(usable: unknown): string {
  return usable === true
    ? "text-[hsl(var(--success-fg))]"
    : "text-[hsl(var(--warning-fg))]";
}

function couponUsableLabel(t: Messages, usable: boolean, reasonCode: string): string {
  const reasons = t.admin.pages.coupons.usableReason as Record<string, string>;
  if (usable) {
    return t.admin.pages.coupons.usable;
  }
  const reason = reasons[reasonCode] || reasonCode || t.labels.common.unknown;
  return t.admin.pages.coupons.unusableWithReason.replace("{reason}", reason);
}

function formatWhen(value: unknown, locale: string): string {
  const raw = text(value);
  if (!raw) {
    return "—";
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleString(locale, { hour12: false });
}

export function AdminCoupons() {
  const { t, locale } = useI18n();
  const { data, flash, setFlash, page, setPage, total, reload } = useData("/api/admin/coupons");
  const coupons = Array.isArray(data?.coupons) ? (data.coupons as Row[]) : [];
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [expandedId, setExpandedId] = useState("");
  /** 启用 / 停用 / 删除 三态；默认启用中。 */
  const [lifecycleFilter, setLifecycleFilter] = useState<"enabled" | "disabled" | "deleted" | "all">("enabled");

  async function generateCode() {
    setBusy(true);
    const result = await postJson("/api/admin/coupons/generate", {});
    setBusy(false);
    if (!result.ok || typeof result.envelope.data?.code !== "string") {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.coupons.msg.generateFail)));
      return;
    }
    const next = typeof result.envelope.data.formatted === "string" ? result.envelope.data.formatted : result.envelope.data.code;
    setCode(next);
    setFlash(okFlash(t.admin.pages.coupons.msg.generated.replace("{code}", next)));
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const rawCode = String(form.get("code") || "").trim();
    const bonus = String(form.get("bonus_amount") || "").trim();
    if (!bonus) {
      setFlash(warnFlash(t.admin.pages.coupons.msg.bonusRequired));
      return;
    }
    setBusy(true);
    const result = await postJson("/api/admin/coupons", {
      code: rawCode || null,
      auto_generate: rawCode === "",
      bonus_amount: bonus,
      max_uses: Number(form.get("max_uses") || 1),
    });
    setBusy(false);
    setFlash(
      resultFlash(
        result.ok,
        t.admin.pages.coupons.msg.created.replace(
          "{suffix}",
          typeof result.envelope.data?.formatted === "string" ? `：${result.envelope.data.formatted}` : "",
        ),
        apiErrorLabel(t, result.envelope, t.admin.pages.coupons.msg.createFail),
      ),
    );
    if (result.ok) {
      formEl.reset();
      setCode("");
      reload();
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.coupons.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.coupons.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form onSubmit={create} className="grid max-w-xl gap-3 text-sm">
        <Field label={t.admin.pages.coupons.code} hint={t.admin.pages.coupons.codeHint}>
          <div className="flex flex-wrap gap-2">
            <input
              name="code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder={t.admin.pages.coupons.codePlaceholder}
              className="min-w-0 flex-1 rounded border border-border bg-background px-3 py-2 font-mono"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              disabled={busy}
              className="rounded border border-border px-3 py-2"
              onClick={() => void generateCode()}
            >
              {t.admin.actions.autoGenerate}
            </button>
          </div>
        </Field>
        <Field label={t.admin.pages.coupons.bonusAmount} hint={t.admin.pages.coupons.bonusAmountHint}>
          <input
            name="bonus_amount"
            required
            placeholder={t.admin.pages.coupons.bonusAmountPlaceholder}
            className="rounded border border-border bg-background px-3 py-2"
          />
        </Field>
        <Field label={t.admin.pages.coupons.maxUses} hint={t.admin.pages.coupons.maxUsesHint}>
          <input name="max_uses" required type="number" min={1} defaultValue={1} className="rounded border border-border bg-background px-3 py-2" />
        </Field>
        <button className="w-fit rounded bg-foreground px-4 py-2 text-background" type="submit" disabled={busy}>
          {t.admin.actions.createAndSave}
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
                  : t.labels.common.deleted;
          const count = coupons.filter((item) => {
            const deleted = item.deleted === true;
            if (value === "all") {
              return true;
            }
            if (value === "deleted") {
              return deleted;
            }
            if (deleted) {
              return false;
            }
            return value === "enabled" ? item.enabled !== false : item.enabled === false;
          }).length;
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
              {label} ({count})
            </button>
          );
        })}
      </div>
      <ul className="space-y-3 text-sm">
        {(() => {
          const visible = coupons.filter((item) => {
            const deleted = item.deleted === true;
            if (lifecycleFilter === "all") {
              return true;
            }
            if (lifecycleFilter === "deleted") {
              return deleted;
            }
            if (deleted) {
              return false;
            }
            return lifecycleFilter === "enabled" ? item.enabled !== false : item.enabled === false;
          });
          if (visible.length === 0) {
            return (
              <li className="rounded-lg border border-dashed border-border px-4 py-6 text-foreground/65">
                {lifecycleFilter === "enabled"
                  ? t.admin.pages.coupons.emptyActive
                  : lifecycleFilter === "disabled"
                    ? t.admin.pages.coupons.emptyDisabled
                    : lifecycleFilter === "deleted"
                      ? t.admin.pages.coupons.emptyDeleted
                      : t.admin.pages.coupons.emptyAll}
              </li>
            );
          }
          return null;
        })()}
        {coupons
          .filter((item) => {
            const deleted = item.deleted === true;
            if (lifecycleFilter === "all") {
              return true;
            }
            if (lifecycleFilter === "deleted") {
              return deleted;
            }
            if (deleted) {
              return false;
            }
            return lifecycleFilter === "enabled" ? item.enabled !== false : item.enabled === false;
          })
          .map((item) => {
            const id = text(item.id);
            const deleted = item.deleted === true;
            const redemptions = Array.isArray(item.redemptions) ? (item.redemptions as Row[]) : [];
            const expanded = expandedId === id;
            return (
              <li key={id} className="space-y-2 rounded border border-border px-3 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <p>
                      <span className="font-mono text-base">{text(item.formatted) || text(item.code)}</span>
                      <span className={`ml-3 font-medium ${couponStatusClass(item.usable)}`}>
                        {couponUsableLabel(t, item.usable === true, text(item.usable_reason))}
                      </span>
                      <span className={`ml-2 ${deleted ? "text-danger" : "text-foreground/60"}`}>
                        ·{" "}
                        {deleted
                          ? t.labels.common.deleted
                          : item.enabled === false
                            ? t.admin.pages.coupons.switchDisabled
                            : t.admin.pages.coupons.switchEnabled}
                      </span>
                    </p>
                    <p className="text-foreground/70">
                      {t.admin.pages.coupons.bonusPrefix} {text(item.bonus_amount)} {text(item.currency)} ·{" "}
                      {t.admin.pages.coupons.maxUsesPrefix} {text(item.max_uses)} · {t.admin.pages.coupons.usedPrefix}{" "}
                      {text(item.used_count)} · {t.admin.pages.coupons.remainingPrefix} {text(item.remaining_uses)}
                      {item.expires_at
                        ? ` · ${t.admin.pages.coupons.expiresPrefix} ${formatWhen(item.expires_at, locale)}`
                        : ` · ${t.admin.pages.coupons.noExpiry}`}
                    </p>
                    <p className="text-foreground/70">
                      {t.admin.pages.coupons.createdPrefix}：{formatWhen(item.created_at, locale)} ·{" "}
                      {text(item.created_by_email) || t.admin.pages.coupons.unknownAdmin}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded border border-border px-3 py-1"
                      onClick={() => setExpandedId(expanded ? "" : id)}
                    >
                      {expanded
                        ? t.admin.actions.collapseDetail
                        : t.admin.pages.coupons.redemptionDetail.replace("{count}", String(redemptions.length))}
                    </button>
                    {deleted ? (
                      <button
                        type="button"
                        className="rounded border border-border px-3 py-1"
                        onClick={() =>
                          void (async () => {
                            if (!window.confirm(t.admin.pages.coupons.msg.confirmRestore)) {
                              return;
                            }
                            const result = await postJson(`/api/admin/coupons/${id}/restore`, {});
                            setFlash(
                              resultFlash(
                                result.ok,
                                t.admin.pages.coupons.msg.restored,
                                apiErrorLabel(t, result.envelope, t.admin.pages.coupons.msg.restoreFail),
                              ),
                            );
                            if (result.ok) {
                              setLifecycleFilter("disabled");
                              reload();
                            }
                          })()
                        }
                      >
                        {t.admin.actions.restore}
                      </button>
                    ) : (
                      <>
                        <button type="button" className="rounded border border-border px-3 py-1" onClick={() => setEditingId(editingId === id ? "" : id)}>
                          {editingId === id ? t.admin.actions.collapseEdit : t.admin.actions.edit}
                        </button>
                        <button
                          type="button"
                          className="rounded border border-border px-3 py-1"
                          onClick={() =>
                            void (async () => {
                              const nextEnabled = item.enabled === false;
                              if (!nextEnabled) {
                                const ok = window.confirm(
                                  t.admin.pages.coupons.msg.confirmDisable.replace(
                                    "{code}",
                                    text(item.formatted) || text(item.code),
                                  ),
                                );
                                if (!ok) {
                                  return;
                                }
                              }
                              const result = await patchJson(`/api/admin/coupons/${id}`, { enabled: nextEnabled });
                              setFlash(
                                resultFlash(
                                  result.ok,
                                  nextEnabled
                                    ? t.admin.pages.coupons.msg.enabled
                                    : t.admin.pages.coupons.msg.disabled,
                                  apiErrorLabel(t, result.envelope, t.admin.pages.coupons.msg.statusFail),
                                ),
                              );
                              if (result.ok) {
                                if (!nextEnabled) {
                                  setLifecycleFilter("enabled");
                                }
                                reload();
                              }
                            })()
                          }
                        >
                          {item.enabled === false ? t.admin.actions.enable : t.admin.actions.disable}
                        </button>
                        <button
                          type="button"
                          className="rounded border border-border px-3 py-1"
                          onClick={() =>
                            void (async () => {
                              if (!window.confirm(t.admin.pages.coupons.msg.confirmDelete)) {
                                return;
                              }
                              const result = await deleteJson(`/api/admin/coupons/${id}`);
                              setFlash(
                                resultFlash(
                                  result.ok,
                                  t.admin.pages.coupons.msg.deleted,
                                  apiErrorLabel(t, result.envelope, t.admin.pages.coupons.msg.deleteFail),
                                ),
                              );
                              if (result.ok) {
                                setLifecycleFilter("enabled");
                                reload();
                              }
                            })()
                          }
                        >
                          {t.admin.actions.delete}
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {expanded ? (
                  <div className="border-t border-border pt-2">
                    <p className="mb-2 font-medium">{t.admin.pages.coupons.redemptionsTitle}</p>
                    {redemptions.length === 0 ? (
                      <p className="text-foreground/70">{t.admin.pages.coupons.emptyRedemptions}</p>
                    ) : (
                      <ul className="space-y-1">
                        {redemptions.map((row) => (
                          <li key={text(row.id)} className="font-mono text-xs sm:text-sm">
                            {formatWhen(row.created_at, locale)} · {text(row.email) || text(row.user_id)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
                {editingId === id && !deleted ? (
                  <form
                    className="grid max-w-md gap-2 border-t border-border pt-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      const formEl = event.currentTarget;
                      void (async () => {
                        const form = new FormData(formEl);
                        const local = String(form.get("expires_at") || "").trim();
                        const clear = form.get("clear_expires") === "on";
                        const payload: Record<string, unknown> = {
                          max_uses: Number(form.get("max_uses") || 1),
                          enabled: form.get("enabled") === "on",
                          clear_expires_at: clear,
                        };
                        if (!clear && local) {
                          payload.expires_at = new Date(local).toISOString();
                        }
                        const result = await patchJson(`/api/admin/coupons/${id}`, payload);
                        setFlash(
                          resultFlash(
                            result.ok,
                            t.admin.pages.coupons.msg.updated,
                            apiErrorLabel(t, result.envelope, t.admin.pages.coupons.msg.updateFail),
                          ),
                        );
                        if (result.ok) {
                          setEditingId("");
                          reload();
                        }
                      })();
                    }}
                  >
                    <Field label={t.admin.pages.coupons.maxUses} hint={t.admin.pages.coupons.maxUsesEditHint}>
                      <input name="max_uses" type="number" min={1} defaultValue={Number(item.max_uses) || 1} className="rounded border border-border bg-background px-3 py-2" />
                    </Field>
                    <Field label={t.admin.pages.coupons.expiresAt} hint={t.admin.pages.coupons.expiresAtHint}>
                      <input name="expires_at" type="datetime-local" className="rounded border border-border bg-background px-3 py-2" />
                    </Field>
                    <label className="flex items-center gap-2">
                      <input name="clear_expires" type="checkbox" />
                      {t.admin.pages.coupons.clearExpires}
                    </label>
                    <label className="flex items-center gap-2">
                      <input name="enabled" type="checkbox" defaultChecked={item.enabled !== false} />
                      {t.admin.pages.coupons.enabledCheckbox}
                    </label>
                    <button type="submit" className="w-fit rounded bg-foreground px-3 py-1.5 text-background">
                      {t.admin.actions.save}
                    </button>
                  </form>
                ) : null}
              </li>
            );
          })}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

export function AdminAnnouncements() {
  const { t } = useI18n();
  const { data, flash, setFlash, page, setPage, total, reload } = useData("/api/admin/announcements");
  const items = Array.isArray(data?.announcements) ? (data.announcements as Row[]) : [];

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const result = await postJson("/api/admin/announcements", {
      slug: String(form.get("slug") || ""),
      title: String(form.get("title") || ""),
      body: String(form.get("body") || ""),
    });
    setFlash(resultFlash(result.ok, t.admin.pages.announcements.msg.savedDraft, apiErrorLabel(t, result.envelope, t.admin.pages.announcements.msg.saveFail)));
    if (result.ok) {
      formEl.reset();
      reload();
    }
  }

  async function publish(id: string, published: boolean) {
    const result = await postJson(`/api/admin/announcements/${id}/publish`, { published });
    setFlash(resultFlash(result.ok, published ? t.admin.pages.announcements.msg.published : t.admin.pages.announcements.msg.unpublished, apiErrorLabel(t, result.envelope, t.admin.pages.announcements.msg.opFail)));
    if (result.ok) {
      reload();
    }
  }

  async function edit(item: Row) {
    const title = window.prompt(t.admin.pages.announcements.promptTitle, text(item.title));
    if (title === null) {
      return;
    }
    const body = window.prompt(t.admin.pages.announcements.promptBody, text(item.body));
    if (body === null) {
      return;
    }
    const result = await patchJson(`/api/admin/announcements/${text(item.id)}`, { title, body });
    setFlash(resultFlash(result.ok, t.admin.pages.announcements.msg.updated, apiErrorLabel(t, result.envelope, t.admin.pages.announcements.msg.opFail)));
    if (result.ok) {
      reload();
    }
  }

  async function remove(id: string) {
    if (!window.confirm(t.admin.pages.announcements.msg.confirmDelete)) {
      return;
    }
    const result = await deleteJson(`/api/admin/announcements/${id}`);
    setFlash(resultFlash(result.ok, t.admin.pages.announcements.msg.deleted, apiErrorLabel(t, result.envelope, t.admin.pages.announcements.msg.deleteFail)));
    if (result.ok) {
      reload();
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.announcements.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.announcements.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form onSubmit={create} className="grid max-w-xl gap-3 text-sm">
        <Field label={t.admin.pages.announcements.slug} hint={t.admin.pages.announcements.slugHint}>
          <input
            name="slug"
            required
            placeholder={t.admin.pages.announcements.slugPlaceholder}
            className="rounded border border-border bg-background px-3 py-2"
          />
        </Field>
        <Field label={t.admin.pages.announcements.titleLabel}>
          <input
            name="title"
            required
            placeholder={t.admin.pages.announcements.titlePlaceholder}
            className="rounded border border-border bg-background px-3 py-2"
          />
        </Field>
        <Field label={t.admin.pages.announcements.bodyLabel} hint={t.admin.pages.announcements.bodyHint}>
          <textarea
            name="body"
            required
            placeholder={t.admin.pages.announcements.bodyPlaceholder}
            className="min-h-24 rounded border border-border bg-background px-3 py-2"
          />
        </Field>
        <button className="w-fit rounded bg-foreground px-4 py-2 text-background" type="submit">
          {t.admin.actions.saveDraft}
        </button>
      </form>
      <ul className="space-y-2 text-sm">
        {items.length === 0 ? <li>{t.admin.pages.announcements.empty}</li> : null}
        {items.map((item) => (
          <li key={text(item.id)} className="flex flex-wrap items-center gap-3">
            <span>
              {text(item.title)} · /announcements/{text(item.slug)} ·{" "}
              {item.published === true
                ? t.admin.pages.announcements.published
                : t.admin.pages.announcements.unpublished}
            </span>
            <button type="button" onClick={() => void publish(text(item.id), item.published !== true)}>
              {item.published === true ? t.admin.actions.unpublishNotice : t.admin.actions.publishNotice}
            </button>
            <button type="button" onClick={() => void edit(item)}>
              {t.admin.actions.edit}
            </button>
            <button type="button" onClick={() => void remove(text(item.id))}>
              {t.admin.actions.delete}
            </button>
          </li>
        ))}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

export function AdminRoutes() {
  const { t } = useI18n();
  const [statusFilter, setStatusFilter] = useState<"active" | "disabled" | "all">("all");
  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [busy, setBusy] = useState(false);
  const path = `/api/admin/routes?status=${statusFilter}${appliedQ ? `&q=${encodeURIComponent(appliedQ)}` : ""
    }`;
  const { data, flash, setFlash, page, setPage, total, reload } = useData(path);
  const routes = Array.isArray(data?.routes) ? (data.routes as Row[]) : [];

  async function toggle(item: Row) {
    const id = text(item.deployment_id);
    if (!id) {
      return;
    }
    const next = item.status === "active" ? "disabled" : "active";
    if (next === "disabled") {
      const ok = window.confirm(
        t.admin.pages.routes.msg.confirmDisable.replace(
          "{name}",
          text(item.display_name) || text(item.model),
        ),
      );
      if (!ok) {
        return;
      }
    }
    setBusy(true);
    const result = await postJson(`/api/admin/deployments/${id}/status`, { status: next });
    setBusy(false);
    setFlash(
      resultFlash(
        result.ok,
        next === "disabled" ? t.admin.pages.routes.msg.disabled : t.admin.pages.routes.msg.enabled,
        apiErrorLabel(t, result.envelope, t.admin.pages.routes.msg.statusFail),
      ),
    );
    if (result.ok) {
      reload();
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.routes.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.routes.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {(
          [
            ["all", t.labels.common.all],
            ["active", t.labels.common.enabled],
            ["disabled", t.labels.common.disabled],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={
              statusFilter === value
                ? "rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-accent"
                : "rounded border border-border px-3 py-1.5 text-foreground/75"
            }
            onClick={() => {
              setStatusFilter(value);
              setPage(1);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <form
        className="flex flex-wrap items-end gap-2 text-sm"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setAppliedQ(q.trim());
        }}
      >
        <label>
          {t.admin.actions.search}
          <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.routes.searchable}</span>
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            className="mt-1 block min-w-56 rounded border border-border bg-background px-3 py-2"
            placeholder={t.admin.pages.routes.searchPlaceholder}
          />
        </label>
        <button type="submit" className="rounded border border-border px-3 py-2">
          {t.admin.actions.query}
        </button>
      </form>
      <ul className="space-y-3 text-sm">
        {routes.length === 0 ? (
          <li className="rounded-md border border-dashed border-border px-3 py-4 text-foreground/70">
            {t.admin.pages.routes.empty}
          </li>
        ) : null}
        {routes.map((item) => {
          const callable = item.callable === true;
          return (
            <li key={text(item.deployment_id) || `${text(item.model)}-${text(item.provider)}`} className="rounded-md border border-border px-3 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <p className="font-medium">
                    {text(item.display_name) || text(item.model)}{" "}
                    <span className="font-mono text-foreground/70">({text(item.model)})</span>
                    {" · "}
                    <span className={callable ? "text-[hsl(var(--success-fg))]" : "text-[hsl(var(--warning-fg))]"}>
                      {callable
                        ? t.admin.pages.routes.callable
                        : item.status === "active"
                          ? t.admin.pages.routes.notCallableProvider
                          : t.admin.pages.routes.notCallableDeploy}
                    </span>
                  </p>
                  <p className="text-foreground/70">
                    → {text(item.provider)}
                    {text(item.provider_status) === "active"
                      ? t.admin.pages.routes.providerOn
                      : t.admin.pages.routes.providerOff}{" "}
                    · {t.admin.pages.routes.priority} {text(item.priority)} · {t.admin.pages.routes.weight}{" "}
                    {text(item.weight)}
                  </p>
                  <p className="break-all text-xs text-foreground/55">{text(item.base_url)}</p>
                </div>
                <button
                  type="button"
                  disabled={busy || !text(item.deployment_id)}
                  className="rounded border border-border px-3 py-1"
                  onClick={() => void toggle(item)}
                >
                  {item.status === "active" ? t.admin.actions.disable : t.admin.actions.enable}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

export function AdminSettings() {
  const { t } = useI18n();
  const { data, flash, reload } = useData("/api/admin/settings");
  const entries = data ? Object.entries(data) : [];
  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.settings.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.settings.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <dl className="grid max-w-lg gap-2 text-sm">
        {entries.map(([key, value]) => (
          <div key={key} className="flex justify-between gap-4 border-b border-border py-2">
            <dt>{key}</dt>
            <dd>
              {typeof value === "boolean"
                ? value
                  ? t.labels.common.yes
                  : t.labels.common.no
                : text(value)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function backupHintText(
  t: Messages,
  code: string,
  path: string,
): string {
  const b = t.admin.pages.backups;
  if (code === "local_pg_dump") {
    return b.hintLocal.replace("{path}", path || "—");
  }
  if (code === "docker") {
    return b.hintDocker;
  }
  if (code === "sql_fallback") {
    return b.hintSql;
  }
  if (code === "unavailable") {
    return b.hintUnavailable;
  }
  return "";
}

export function AdminBackups() {
  const { t } = useI18n();
  const { data, flash, setFlash, reload } = useData("/api/admin/backups");
  const backups = Array.isArray(data?.backups) ? (data.backups as Row[]) : [];
  const canBackup = data?.can_backup === true;
  const hintCode = text(data?.hint_code) || (text(data?.hint) ? "legacy" : "");
  const hint =
    hintCode === "legacy"
      ? text(data?.hint)
      : backupHintText(t, hintCode, text(data?.pg_dump_path));
  const [busy, setBusy] = useState(false);
  const b = t.admin.pages.backups;

  async function run() {
    if (!canBackup) {
      setFlash(errFlash(hint || b.cannotBackup));
      return;
    }
    setBusy(true);
    setFlash(infoFlash(b.running));
    const result = await postJson("/api/admin/backups", {});
    setBusy(false);
    const method = text(result.envelope.data?.method);
    const methodNote =
      method === "docker" ? b.methodDocker : method === "pg_dump" ? b.methodPgDump : method === "sql" ? b.methodSql : "";
    setFlash(
      resultFlash(
        result.ok,
        b.created.replace("{name}", text(result.envelope.data?.name)).replace("{method}", methodNote),
        apiErrorLabel(t, result.envelope, b.createFail),
      ),
    );
    if (result.ok) {
      reload();
    }
  }

  async function remove(name: string) {
    if (!window.confirm(b.confirmDelete.replace("{name}", name))) {
      return;
    }
    const result = await deleteJson(`/api/admin/backups/${encodeURIComponent(name)}`);
    setFlash(resultFlash(result.ok, b.deleted, apiErrorLabel(t, result.envelope, b.deleteFail)));
    if (result.ok) {
      reload();
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.backups.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.backups.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-foreground/60">{t.admin.pages.backups.pgDump}</dt>
          <dd>
            {data?.pg_dump === true
              ? `${t.admin.pages.backups.found}${text(data?.pg_dump_path) ? `：${text(data.pg_dump_path)}` : ""}`
              : t.admin.pages.backups.notFound}
          </dd>
        </div>
        <div>
          <dt className="text-foreground/60">{t.admin.pages.backups.dockerFallback}</dt>
          <dd>
            {data?.backup_allow_docker === false
              ? t.admin.pages.backups.dockerDisabled
              : data?.docker_available === true
                ? t.admin.pages.backups.dockerOk
                : t.admin.pages.backups.dockerMissing}
          </dd>
        </div>
        <div>
          <dt className="text-foreground/60">{t.admin.pages.backups.sqlFallback}</dt>
          <dd>{data?.sql_fallback === true ? t.admin.pages.backups.sqlOk : t.admin.pages.backups.sqlNo}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-foreground/60">{t.admin.pages.backups.backupDir}</dt>
          <dd className="break-all font-mono text-xs">{text(data?.backup_dir) || t.admin.actions.none}</dd>
        </div>
      </dl>
      {hint ? (
        <p
          className={
            canBackup
              ? "rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground/75"
              : "rounded-md border border-[hsl(var(--warning-fg))]/30 bg-[hsl(var(--warning-fg))]/5 px-3 py-2 text-sm"
          }
        >
          {hint}
        </p>
      ) : null}
      <button
        type="button"
        disabled={busy || data === null || !canBackup}
        className="rounded bg-foreground px-4 py-2 text-sm text-background disabled:opacity-50"
        onClick={() => void run()}
      >
        {busy ? t.admin.pages.backups.running : t.admin.pages.backups.run}
      </button>
      <ul className="space-y-2 text-sm">
        {backups.length === 0 ? (
          <li className="rounded-md border border-dashed border-border px-3 py-4 text-foreground/70">
            {t.admin.pages.backups.empty}
          </li>
        ) : null}
        {backups.map((item) => (
          <li key={text(item.name)} className="flex flex-wrap items-center gap-3 rounded-md border border-border px-3 py-2">
            <span className="min-w-0 flex-1 break-all">
              {text(item.name)} · {text(item.bytes)} {t.admin.pages.backups.bytes}
              {text(item.modified_at) ? ` · ${text(item.modified_at)}` : ""}
            </span>
            <button type="button" className="rounded border border-border px-2 py-1 text-xs" onClick={() => void remove(text(item.name))}>
              {t.admin.actions.delete}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AdminMargin() {
  const { t } = useI18n();
  const { data, flash, reload } = useData("/api/admin/margin");
  const reconcile = data?.reconcile && typeof data.reconcile === "object" ? (data.reconcile as Row) : {};
  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.margin.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.margin.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      {data ? (
        <dl className="grid max-w-md gap-2 text-sm">
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.margin.userCharge}</dt>
            <dd>{text(data.user_charge)}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.margin.providerCost}</dt>
            <dd>{text(data.provider_cost)}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-2">
            <dt>{t.admin.pages.margin.margin}</dt>
            <dd>{text(data.margin)}</dd>
          </div>
          {Object.entries(reconcile).map(([status, count]) => (
            <div key={status} className="flex justify-between border-b border-border py-2">
              <dt>
                {t.admin.pages.margin.orderPrefix}
                {statusLabel(t, "reconcile", status)}
              </dt>
              <dd>{text(count)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

export function AdminContent() {
  const { t } = useI18n();
  const { data, flash, setFlash, page, setPage, total, reload } = useData("/api/admin/content-safety");
  const records = Array.isArray(data?.records) ? (data.records as Row[]) : [];

  async function toggle() {
    const result = await postJson("/api/admin/content-safety", { enabled: data?.enabled !== true });
    setFlash(resultFlash(result.ok, t.admin.pages.content.msg.saved, apiErrorLabel(t, result.envelope, t.admin.pages.content.msg.saveFail)));
    if (result.ok) {
      reload();
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.content.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.content.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <button type="button" className="rounded bg-foreground px-4 py-2 text-sm text-background" onClick={() => void toggle()}>
        {data?.enabled === true ? t.admin.pages.content.toggleOff : t.admin.pages.content.toggleOn}
      </button>
      <ul className="space-y-2 text-sm">
        {records.length === 0 ? <li>{t.admin.pages.content.empty}</li> : null}
        {records.map((item) => (
          <li key={text(item.id)}>
            {text(item.model_name)} · {text(item.category)} · {text(item.summary_hash).slice(0, 12)}
          </li>
        ))}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

export function AdminTasks() {
  const { t } = useI18n();
  const { data, flash, setFlash, page, setPage, total, reload } = useData("/api/admin/tasks");
  const jobs = Array.isArray(data?.jobs) ? (data.jobs as string[]) : [];
  const runs = Array.isArray(data?.runs) ? (data.runs as Row[]) : [];
  const failed = Array.isArray(data?.failed) ? (data.failed as Row[]) : [];
  const jobLabel = (name: string) =>
    t.admin.pages.tasks.jobs[name as keyof typeof t.admin.pages.tasks.jobs] || name;

  async function ping() {
    const result = await postJson("/api/admin/tasks/ping", {});
    setFlash(resultFlash(result.ok, t.admin.pages.tasks.msg.pingOk, apiErrorLabel(t, result.envelope, t.admin.pages.tasks.msg.pingFail)));
    if (result.ok) {
      reload();
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.tasks.title}</h1>
            <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.tasks.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <ul className="space-y-1 text-sm">
        {jobs.map((name) => (
          <li key={name}>{jobLabel(name)}</li>
        ))}
      </ul>
      <button type="button" className="rounded bg-foreground px-4 py-2 text-sm text-background" onClick={() => void ping()}>
        {t.admin.actions.runPing}
      </button>
      <h2 className="text-lg font-medium">{t.admin.pages.tasks.recent}</h2>
      <ul className="space-y-1 text-sm">
        {runs.length === 0 ? <li>{t.admin.pages.tasks.emptyRuns}</li> : null}
        {runs.map((item) => (
          <li key={text(item.id)}>
            {jobLabel(text(item.name))} ·{" "}
            {item.status === "succeeded" ? statusLabel(t, "common", "success") : statusLabel(t, "common", "failed")} ·{" "}
            {text(item.detail)}
          </li>
        ))}
      </ul>
      <h2 className="text-lg font-medium">{t.admin.pages.tasks.failed}</h2>
      <ul className="space-y-1 text-sm">
        {failed.length === 0 ? <li>{t.admin.pages.tasks.emptyFailed}</li> : null}
        {failed.map((item) => (
          <li key={text(item.id)}>{text(item.name)} · {text(item.detail)}</li>
        ))}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}
