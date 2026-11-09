"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  loadFlash,
  resultFlash,
  warnFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { RefreshButton } from "@/components/ui/refresh-button";
import { errorMessage, getJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { ledgerDirectionLabel, ledgerReasonLabel, ledgerTypeLabel } from "@/lib/ledger-label";

const PAGE_SIZE = 20;

type BalanceRow = {
  user_id: string;
  email: string;
  currency: string;
  balance: string;
  held: string;
  frozen: string;
  available: string;
};
type EntryRow = { id: string; email: string; entry_type: string; direction: string; amount: string; currency: string; reason: string };

async function pullLedger(page: number, loadFail: string): Promise<{ balances: BalanceRow[]; entries: EntryRow[]; total: number; message: string }> {
  const result = await getJson(`/api/admin/ledger?page=${page}&page_size=${PAGE_SIZE}`);
  if (!result.ok || !result.envelope.data) {
    return { balances: [], entries: [], total: 0, message: errorMessage(result.envelope, loadFail) };
  }
  const total =
    typeof result.envelope.data.total === "number"
      ? result.envelope.data.total
      : typeof result.envelope.data.entry_total === "number"
        ? result.envelope.data.entry_total
        : 0;
  return {
    balances: readBalances(result.envelope.data.balances),
    entries: readEntries(result.envelope.data.entries),
    total,
    message: "",
  };
}

export function AdminLedger() {
  const { t } = useI18n();
  const [balances, setBalances] = useState<BalanceRow[]>([]);
  const [entries, setEntries] = useState<EntryRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { flash, setFlash } = useBootFlash(t.admin.pages.ledger.loading);
  const [busy, setBusy] = useState(false);

  async function load() {
    const next = await pullLedger(page, t.admin.pages.ledger.loadFail);
    setBalances(next.balances);
    setEntries(next.entries);
    setTotal(next.total);
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullLedger(page, t.admin.pages.ledger.loadFail);
      setBalances(next.balances);
      setEntries(next.entries);
      setTotal(next.total);
      setFlash(loadFlash(next.message));
    })();
  }, [page]);

  async function adjust(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const userId = String(form.get("user_id") || "");
    const amount = String(form.get("amount") || "");
    const direction = String(form.get("direction") || "C");
    const reason = String(form.get("reason") || "");
    if (!userId) {
      setFlash(warnFlash(t.admin.pages.ledger.selectCustomer));
      return;
    }
    setBusy(true);
    const result = await postJson(
      "/api/admin/ledger/adjust",
      { user_id: userId, amount, direction, reason },
      { "Idempotency-Key": crypto.randomUUID() },
    );
    setBusy(false);
    setFlash(
      resultFlash(
        result.ok,
        t.admin.pages.ledger.adjusted,
        apiErrorLabel(t, result.envelope, t.admin.pages.ledger.adjustFail),
      ),
    );
    if (result.ok) {
      formEl.reset();
      await load();
    }
  }

  return (
    <section className="space-y-8">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.ledger.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.ledger.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      <form className="grid max-w-2xl gap-3 rounded-md border border-border p-4 text-sm sm:grid-cols-2" onSubmit={adjust}>
        <label className="sm:col-span-2">
          {t.admin.pages.ledger.customer}
          <select name="user_id" required className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-foreground">
            <option value="">{t.admin.pages.ledger.selectAccount}</option>
            {balances.map((row) => (
              <option key={`${row.user_id}-${row.currency}`} value={row.user_id}>
                {row.email} · {t.admin.pages.ledger.available} {row.available} {row.currency}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.admin.pages.ledger.direction}
          <select name="direction" className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-foreground" defaultValue="C">
            <option value="C">{t.admin.pages.ledger.credit}</option>
            <option value="D">{t.admin.pages.ledger.debit}</option>
          </select>
        </label>
        <label>
          {t.admin.pages.ledger.amount}
          <input name="amount" required placeholder="1.00" className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
        </label>
        <label className="sm:col-span-2">
          {t.admin.pages.ledger.reason}
          <input name="reason" required minLength={2} className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
        </label>
        <button type="submit" disabled={busy} className="w-fit rounded bg-foreground px-4 py-2 text-background">
          {t.admin.actions.submitAdjust}
        </button>
      </form>
      <div>
        <h2 className="text-lg font-medium">{t.admin.pages.ledger.balance}</h2>
        {balances.length === 0 ? <p className="mt-2 text-sm text-foreground/70">{t.admin.pages.ledger.emptyActive}</p> : null}
        <table className="mt-3 w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-foreground/70">
              <th className="py-2 pr-3 font-medium">{t.admin.pages.ledger.customer}</th>
              <th className="py-2 pr-3 font-medium">{t.admin.pages.ledger.balance}</th>
              <th className="py-2 pr-3 font-medium">{t.admin.pages.ledger.held}</th>
              <th className="py-2 pr-3 font-medium">{t.admin.pages.ledger.frozen}</th>
              <th className="py-2 font-medium">{t.admin.pages.ledger.available}</th>
            </tr>
          </thead>
          <tbody>
            {balances.map((row) => (
              <tr key={`${row.email}-${row.currency}`} className="border-b border-border">
                <td className="py-2 pr-3">{row.email}</td>
                <td className="py-2 pr-3">
                  {row.balance} {row.currency}
                </td>
                <td className="py-2 pr-3">{row.held}</td>
                <td className="py-2 pr-3">{row.frozen}</td>
                <td className="py-2">{row.available}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <h2 className="text-lg font-medium">{t.admin.pages.ledger.entries}</h2>
        {entries.length === 0 ? <p className="mt-2 text-sm text-foreground/70">{t.admin.pages.ledger.emptyAll}</p> : null}
        <ul className="mt-3 space-y-2">
          {entries.map((entry) => (
            <li key={entry.id} className="rounded-md border border-border px-3 py-2 text-sm">
              {entry.email} · {ledgerTypeLabel(t, entry.entry_type)} · {ledgerDirectionLabel(t, entry.direction)} ·{" "}
              {entry.amount} {entry.currency} · {ledgerReasonLabel(t, entry.reason)}
            </li>
          ))}
        </ul>
        <div className="mt-4">
          <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
        </div>
      </div>
    </section>
  );
}

function readBalances(value: unknown): BalanceRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.email !== "string" || typeof row.available !== "string") {
      return [];
    }
    return [
      {
        user_id: typeof row.user_id === "string" ? row.user_id : "",
        email: row.email,
        currency: typeof row.currency === "string" ? row.currency : "",
        balance: typeof row.balance === "string" ? row.balance : "",
        held: typeof row.held === "string" ? row.held : "",
        frozen: typeof row.frozen === "string" ? row.frozen : "",
        available: row.available,
      },
    ];
  });
}

function readEntries(value: unknown): EntryRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.email !== "string") {
      return [];
    }
    return [
      {
        id: row.id,
        email: row.email,
        entry_type: typeof row.entry_type === "string" ? row.entry_type : "",
        direction: typeof row.direction === "string" ? row.direction : "",
        amount: typeof row.amount === "string" ? row.amount : "",
        currency: typeof row.currency === "string" ? row.currency : "",
        reason: typeof row.reason === "string" ? row.reason : "",
      },
    ];
  });
}
