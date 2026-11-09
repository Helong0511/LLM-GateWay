"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
  loadFlash,
  okFlash,
  resultFlash,
  warnFlash,
  type FlashMessage,
} from "@/components/ui/flash";
import { Field } from "@/components/ui/field";
import { PageControls } from "@/components/page-controls";
import { RefreshButton } from "@/components/ui/refresh-button";
import { errorMessage, getJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

const PAGE_SIZE = 20;
const CHANNELS = ["stripe", "usdt", "mock", "wechat", "alipay"] as const;
const PAYMENT_STATUSES = ["pending", "confirming", "completed", "overpaid", "closed", "expired", "refunded"] as const;
const RECONCILE_STATUSES = ["unchecked", "matched", "disputed"] as const;

type AdminOrder = {
  order_no: string;
  email: string;
  channel: string;
  status: string;
  reconcile_status: string;
  amount: string;
  currency: string;
};

function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

async function pullOrders(
  page: number,
  filters: { q: string; status: string; reconcile: string },
  loadFail: string,
): Promise<{ orders: AdminOrder[]; total: number; message: string }> {
  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (filters.q.trim()) {
    params.set("q", filters.q.trim());
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.reconcile) {
    params.set("reconcile_status", filters.reconcile);
  }
  const result = await getJson(`/api/admin/orders?${params.toString()}`);
  if (!result.ok || !result.envelope.data) {
    return { orders: [], total: 0, message: errorMessage(result.envelope, loadFail) };
  }
  return {
    orders: readOrders(result.envelope.data.orders),
    total: typeof result.envelope.data.total === "number" ? result.envelope.data.total : 0,
    message: "",
  };
}

export function AdminOrders() {
  const { t } = useI18n();
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { flash, setFlash } = useBootFlash(t.admin.pages.orders.loading);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [reconcileFilter, setReconcileFilter] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [appliedStatus, setAppliedStatus] = useState("");
  const [appliedReconcile, setAppliedReconcile] = useState("");

  async function load() {
    const next = await pullOrders(page, { q: appliedQ, status: appliedStatus, reconcile: appliedReconcile }, t.admin.pages.orders.loadFail);
    setOrders(next.orders);
    setTotal(next.total);
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullOrders(page, { q: appliedQ, status: appliedStatus, reconcile: appliedReconcile }, t.admin.pages.orders.loadFail);
      setOrders(next.orders);
      setTotal(next.total);
      setFlash(loadFlash(next.message));
    })();
  }, [page, appliedQ, appliedStatus, appliedReconcile]);

  async function cancelOrder(orderNo: string) {
    if (!window.confirm(t.admin.pages.orders.msg.confirmClose.replace("{orderNo}", orderNo))) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/orders/${orderNo}/cancel`, {});
    setBusy(false);
    setFlash(resultFlash(result.ok, t.admin.pages.orders.msg.closed, apiErrorLabel(t, result.envelope, t.admin.pages.orders.msg.closeFail)));
    if (result.ok) {
      await load();
    }
  }

  async function markReconcile(orderNo: string, status: "matched" | "disputed" | "unchecked") {
    setBusy(true);
    const result = await postJson(`/api/admin/orders/${orderNo}/reconcile`, { status });
    setBusy(false);
    const tip =
      status === "matched"
        ? t.admin.pages.ordersExtra.markedMatched
        : status === "disputed"
          ? t.admin.pages.ordersExtra.markedDisputed
          : t.admin.pages.ordersExtra.markedUnchecked;
    setFlash(resultFlash(result.ok, tip, apiErrorLabel(t, result.envelope, t.admin.pages.ordersExtra.reconcileFail)));
    if (result.ok) {
      await load();
    }
  }

  async function reconcileBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const channel = String(form.get("channel") || "");
    const billDate = String(form.get("bill_date") || "");
    const raw = String(form.get("rows") || "").trim();
    const rows = raw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [order_no, amount] = line.split(/[\s,，\t]+/);
        return { order_no: order_no || "", amount: amount || "" };
      })
      .filter((row) => row.order_no && row.amount);
    if (rows.length === 0) {
      setFlash(warnFlash(t.admin.pages.orders.msg.batchNeedRows));
      return;
    }
    setBusy(true);
    const result = await postJson("/api/admin/payments/reconcile", {
      channel,
      bill_date: billDate,
      rows,
    });
    setBusy(false);
    if (!result.ok || !result.envelope.data) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.orders.msg.batchFail)));
      return;
    }
    const data = result.envelope.data as Record<string, unknown>;
    setFlash(okFlash(t.admin.pages.orders.msg.batchOk.replace("{matched}", String(data.matched ?? 0)).replace("{disputed}", String(data.disputed ?? 0))));
    formEl.reset();
    await load();
  }

  const credited = (status: string) => status === "completed" || status === "overpaid";

  return (
    <section className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.orders.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.orders.lead}</p>
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
          setAppliedReconcile(reconcileFilter);
        }}
      >
        <label>
          {t.admin.actions.emailOrOrder}
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={t.admin.actions.fuzzy}
            className="mt-1 block min-w-56 rounded border border-border bg-transparent px-3 py-2"
          />
        </label>
        <label>
          {t.admin.actions.paymentStatus}
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="mt-1 block rounded border border-border bg-background px-3 py-2 text-foreground"
          >
            <option value="">{t.labels.common.all}</option>
            {PAYMENT_STATUSES.map((code) => (
              <option key={code} value={code}>
                {statusLabel(t, "payment", code)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.admin.actions.reconcile}
          <select
            value={reconcileFilter}
            onChange={(event) => setReconcileFilter(event.target.value)}
            className="mt-1 block rounded border border-border bg-background px-3 py-2 text-foreground"
          >
            <option value="">{t.labels.common.all}</option>
            {RECONCILE_STATUSES.map((code) => (
              <option key={code} value={code}>
                {statusLabel(t, "reconcile", code)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="rounded border border-border px-3 py-2">
          {t.admin.actions.query}
        </button>
      </form>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-foreground/70">
            <th className="py-2 pr-3 font-medium">{t.admin.pages.orders.order}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.orders.customer}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.orders.channel}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.users.status}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.actions.reconcile}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.orders.amount}</th>
            <th className="py-2 font-medium">{t.admin.pages.users.actions}</th>
          </tr>
        </thead>
        <tbody>
          {orders.length === 0 ? (
            <tr>
              <td colSpan={7} className="py-6 text-foreground/70">
                {t.admin.actions.empty}
              </td>
            </tr>
          ) : null}
          {orders.map((order) => (
            <tr key={order.order_no} className="border-b border-border">
              <td className="py-2 pr-3 font-mono text-xs">{order.order_no}</td>
              <td className="py-2 pr-3">{order.email}</td>
              <td className="py-2 pr-3">{statusLabel(t, "channel", order.channel)}</td>
              <td className="py-2 pr-3">{statusLabel(t, "payment", order.status)}</td>
              <td className="py-2 pr-3">{statusLabel(t, "reconcile", order.reconcile_status)}</td>
              <td className="py-2 pr-3">
                {order.amount} {order.currency}
              </td>
              <td className="py-2">
                <div className="flex flex-wrap gap-1">
                  {order.status === "pending" ? (
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded border border-border px-2 py-1 text-xs"
                      onClick={() => void cancelOrder(order.order_no)}
                    >
                      {t.admin.actions.close}
                    </button>
                  ) : null}
                  {credited(order.status) ? (
                    <>
                      {order.reconcile_status !== "matched" ? (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-border px-2 py-1 text-xs"
                          onClick={() => void markReconcile(order.order_no, "matched")}
                        >
                          {t.admin.actions.match}
                        </button>
                      ) : null}
                      {order.reconcile_status !== "disputed" ? (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-border px-2 py-1 text-xs"
                          onClick={() => void markReconcile(order.order_no, "disputed")}
                        >
                          {t.admin.actions.dispute}
                        </button>
                      ) : null}
                      {order.reconcile_status !== "unchecked" ? (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-border px-2 py-1 text-xs"
                          onClick={() => void markReconcile(order.order_no, "unchecked")}
                        >
                          {t.admin.actions.reset}
                        </button>
                      ) : null}
                    </>
                  ) : null}
                  {order.status !== "pending" && !credited(order.status) ? t.admin.actions.none : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />

      <details className="max-w-2xl rounded-md border border-border p-4 text-sm">
        <summary className="cursor-pointer font-medium">{t.admin.pages.orders.batchTitle}</summary>
        <p className="mt-2 text-xs text-foreground/60">{t.admin.pages.orders.batchLead}</p>
        <form className="mt-3 grid gap-3" onSubmit={(event) => void reconcileBatch(event)}>
          <Field label={t.admin.pages.orders.channel}>
            <select
              name="channel"
              required
              defaultValue="stripe"
              className="rounded border border-border bg-background px-3 py-2 text-foreground"
            >
              {CHANNELS.map((code) => (
                <option key={code} value={code}>
                  {statusLabel(t, "channel", code)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t.admin.pages.orders.billDate}>
            <input
              name="bill_date"
              required
              type="date"
              defaultValue={todayIso()}
              className="rounded border border-border bg-transparent px-3 py-2"
            />
          </Field>
          <Field label={t.admin.pages.orders.billRows} hint={t.admin.pages.orders.billRowsHint}>
            <textarea
              name="rows"
              required
              placeholder={"P20261029001 10.00\nP20261029002 20.00"}
              className="min-h-24 rounded border border-border bg-transparent px-3 py-2 font-mono"
            />
          </Field>
          <button type="submit" disabled={busy} className="w-fit rounded bg-foreground px-4 py-2 text-background">
            {t.admin.pages.orders.batchSubmit}
          </button>
        </form>
      </details>
    </section>
  );
}

function readOrders(value: unknown): AdminOrder[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.order_no !== "string" || typeof row.email !== "string") {
      return [];
    }
    return [
      {
        order_no: row.order_no,
        email: row.email,
        channel: typeof row.channel === "string" ? row.channel : "",
        status: typeof row.status === "string" ? row.status : "",
        reconcile_status: typeof row.reconcile_status === "string" ? row.reconcile_status : "unchecked",
        amount: typeof row.amount === "string" ? row.amount : "",
        currency: typeof row.currency === "string" ? row.currency : "",
      },
    ];
  });
}
