"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import { PageControls } from "@/components/page-controls";
import { Button } from "@/components/ui/button";
import {
  FlashBanner,
  errFlash,
    okFlash,
  resultFlash,
  warnFlash,
  type FlashMessage,
} from "@/components/ui/flash";
import { errorMessage, getJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { ledgerDirectionLabel, ledgerReasonLabel, ledgerTypeLabel } from "@/lib/ledger-label";
import { displayMoney } from "@/lib/money";
import { billingNoteLabel, paymentWarningLabel } from "@/lib/notify-label";
import { productDisplayName } from "@/lib/product-label";
import { statusLabel } from "@/lib/status-label";

const PAGE_SIZE = 20;

type Product = { id: string; name: string; amount: string; currency: string };
type Entry = { id: string; entry_type: string; direction: string; amount: string; created_at: string; reason: string };
type Order = { order_no: string; channel: string; status: string; amount: string; pay_address?: string | null; warning?: string | null };
type BillingSnapshot = {
  note: string;
  available: string | null;
  currency: string;
  entries: Entry[];
  entryTotal: number;
  products: Product[];
  orders: Order[];
  orderTotal: number;
};

async function pullBilling(entryPage: number, orderPage: number, loadFail: string): Promise<BillingSnapshot> {
  const result = await getJson(`/api/billing?page=${entryPage}&page_size=${PAGE_SIZE}`);
  if (!result.ok || !result.envelope.data) {
    return {
      note: errorMessage(result.envelope, loadFail),
      available: null,
      currency: "USD",
      entries: [],
      entryTotal: 0,
      products: [],
      orders: [],
      orderTotal: 0,
    };
  }
  const data = result.envelope.data;
  const listed = await getJson("/api/payments/products");
  const history = await getJson(`/api/payments/orders?page=${orderPage}&page_size=${PAGE_SIZE}`);
  return {
    note: typeof data.note === "string" ? data.note : "",
    available: typeof data.available === "string" ? data.available : null,
    currency: typeof data.currency === "string" ? data.currency : "USD",
    entries: readEntries(data.entries),
    entryTotal: typeof data.total === "number" ? data.total : 0,
    products: listed.ok && listed.envelope.data ? readProducts(listed.envelope.data.products) : [],
    orders: history.ok && history.envelope.data ? readOrders(history.envelope.data.orders) : [],
    orderTotal:
      history.ok && history.envelope.data && typeof history.envelope.data.total === "number" ? history.envelope.data.total : 0,
  };
}

export function BillingPanel() {
  const { t } = useI18n();
  const { flash, setFlash } = useBootFlash(t.console.billing.loading);
  const [available, setAvailable] = useState<string | null>(null);
  const [currency, setCurrency] = useState("USD");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [entryPage, setEntryPage] = useState(1);
  const [entryTotal, setEntryTotal] = useState(0);
  const [products, setProducts] = useState<Product[]>([]);
  const [order, setOrder] = useState<Order | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [orderPage, setOrderPage] = useState(1);
  const [orderTotal, setOrderTotal] = useState(0);
  const [busy, setBusy] = useState(false);

  function apply(next: BillingSnapshot) {
    setAvailable(next.available);
    setCurrency(next.currency);
    setEntries(next.entries);
    setEntryTotal(next.entryTotal);
    setProducts(next.products);
    setOrders(next.orders);
    setOrderTotal(next.orderTotal);
    if (next.available === null && next.note) {
      setFlash(errFlash(billingNoteLabel(t, next.note)));
    }
  }

  async function load() {
    const next = await pullBilling(entryPage, orderPage, t.console.billing.loadFail);
    apply(next);
    return next;
  }

  useEffect(() => {
    void (async () => {
      const next = await pullBilling(entryPage, orderPage, t.console.billing.loadFail);
      apply(next);
      if (!(next.available === null && next.note)) {
        setFlash(null);
      }
    })();
  }, [entryPage, orderPage]);

  async function recharge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const selected = form.get("product_id");
    const channel = form.get("channel");
    if (typeof selected !== "string" || typeof channel !== "string") {
      return;
    }
    setBusy(true);
    const result = await postJson(
      "/api/payments/orders",
      { product_id: selected, channel },
      { "Idempotency-Key": crypto.randomUUID() },
    );
    setBusy(false);
    if (!result.ok || !result.envelope.data) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.billing.msg.createFail)));
      return;
    }
    setOrder(readOrder(result.envelope.data));
    await load();
    setFlash(warnFlash(t.console.billing.msg.createdMock));
  }

  async function confirmMock() {
    if (!order) {
      return;
    }
    setBusy(true);
    const result = await postJson("/api/payments/mock/confirm", { order_no: order.order_no });
    setBusy(false);
    if (!result.ok || !result.envelope.data) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.billing.msg.confirmFail)));
      return;
    }
    setOrder(readOrder(result.envelope.data));
    await load();
    setFlash(okFlash(t.console.billing.msg.mockConfirmed));
  }

  async function cancelPending(orderNo: string) {
    if (!window.confirm(t.console.billing.msg.confirmCancel.replace("{orderNo}", orderNo))) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/payments/orders/${orderNo}/cancel`, {});
    setBusy(false);
    if (result.ok) {
      if (order?.order_no === orderNo) {
        setOrder(null);
      }
      await load();
    }
    setFlash(resultFlash(result.ok, t.console.billing.msg.cancelled, apiErrorLabel(t, result.envelope, t.console.billing.msg.cancelFail)));
  }

  const b = t.console.billing;

  return (
    <section className="max-w-3xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">{b.title}</h1>
        <p className="text-sm text-foreground/70">{b.lead}</p>
        {flash ? <FlashBanner flash={flash} compact /> : null}
        <p className="text-2xl font-semibold">{displayMoney(available, currency)}</p>
      </div>
      <form className="space-y-3 rounded-md border border-border p-4" onSubmit={recharge}>
        <h2 className="text-lg font-medium">{b.topUp}</h2>
        {products.length === 0 ? <p className="text-sm text-foreground/70">{b.emptyProducts}</p> : null}
        {products.map((product) => (
          <label key={product.id} className="flex items-center gap-2 text-sm">
            <input type="radio" name="product_id" value={product.id} required />
            <span>
              {productDisplayName(t, product.name)} · {product.amount} {product.currency}
            </span>
          </label>
        ))}
        <label className="block text-sm">
          {b.channel}
          <select name="channel" className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground" defaultValue="mock">
            <option value="mock">{statusLabel(t, "channel", "mock")}</option>
            <option value="stripe">{statusLabel(t, "channel", "stripe")}</option>
            <option value="usdt">{statusLabel(t, "channel", "usdt")}</option>
          </select>
        </label>
        <Button type="submit" disabled={busy || products.length === 0}>
          {busy ? b.processing : b.createOrder}
        </Button>
      </form>
      {order ? (
        <div className="space-y-2 rounded-md border border-border p-4 text-sm">
          <p>
            {b.order} {order.order_no}
          </p>
          <p>
            {statusLabel(t, "channel", order.channel)} · {statusLabel(t, "payment", order.status)} · {order.amount}
          </p>
          {order.pay_address ? (
            <p className="break-all">
              {b.payAddress} {order.pay_address}
            </p>
          ) : null}
          {order.warning ? <p>{paymentWarningLabel(t, order.warning)}</p> : null}
          {order.channel === "mock" && order.status === "pending" ? (
            <Button type="button" onClick={() => void confirmMock()} disabled={busy}>
              {b.confirmMock}
            </Button>
          ) : null}
          {order.status === "pending" ? (
            <Button type="button" variant="outline" onClick={() => void cancelPending(order.order_no)} disabled={busy}>
              {b.cancelOrder}
            </Button>
          ) : null}
        </div>
      ) : null}
      <div className="space-y-2">
        <h2 className="text-lg font-medium">{b.orders}</h2>
        {orders.length === 0 ? <p className="text-sm text-foreground/70">{b.emptyOrders}</p> : null}
        <ul className="space-y-2">
          {orders.map((item) => (
            <li key={item.order_no} className="flex flex-wrap items-center gap-3 rounded-md border border-border px-3 py-2 text-sm">
              <span>
                {item.order_no} · {statusLabel(t, "channel", item.channel)} · {statusLabel(t, "payment", item.status)} ·{" "}
                {item.amount}
              </span>
              {item.status === "pending" ? (
                <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void cancelPending(item.order_no)}>
                  {t.admin.actions.cancel}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
        <PageControls page={orderPage} pageSize={PAGE_SIZE} total={orderTotal} onPageChange={setOrderPage} />
      </div>
      <div className="space-y-2">
        <h2 className="text-lg font-medium">{b.entries}</h2>
        {entries.length === 0 ? <p className="text-sm text-foreground/70">{b.emptyEntries}</p> : null}
        <ul className="space-y-2">
          {entries.map((entry) => (
            <li key={entry.id} className="rounded-md border border-border px-3 py-2 text-sm">
              {ledgerTypeLabel(t, entry.entry_type)} · {ledgerDirectionLabel(t, entry.direction)} · {entry.amount} ·{" "}
              {ledgerReasonLabel(t, entry.reason)}
            </li>
          ))}
        </ul>
        <PageControls page={entryPage} pageSize={PAGE_SIZE} total={entryTotal} onPageChange={setEntryPage} />
      </div>
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
    return [{ id: row.id, name: row.name, amount: row.amount, currency: typeof row.currency === "string" ? row.currency : "" }];
  });
}

function readEntries(value: unknown): Entry[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.entry_type !== "string" || typeof row.amount !== "string") {
      return [];
    }
    return [
      {
        id: row.id,
        entry_type: row.entry_type,
        direction: typeof row.direction === "string" ? row.direction : "",
        amount: row.amount,
        created_at: typeof row.created_at === "string" ? row.created_at : "",
        reason: typeof row.reason === "string" ? row.reason : "",
      },
    ];
  });
}

function readOrders(value: unknown): Order[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    return [readOrder(item as Record<string, unknown>)].filter((row) => row.order_no !== "");
  });
}

function readOrder(data: Record<string, unknown>): Order {
  return {
    order_no: typeof data.order_no === "string" ? data.order_no : "",
    channel: typeof data.channel === "string" ? data.channel : "",
    status: typeof data.status === "string" ? data.status : "",
    amount: typeof data.amount === "string" ? data.amount : "",
    pay_address: typeof data.pay_address === "string" ? data.pay_address : null,
    warning: typeof data.warning === "string" ? data.warning : null,
  };
}
