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

type RefundRow = {
  id: string;
  order_no: string;
  email: string;
  amount: string;
  currency: string;
  status: string;
  destination_address: string;
  reason: string;
  requested_by: string;
  reviewed_by: string | null;
};

type RefundPage = {
  actorId: string;
  canRequest: boolean;
  canExecute: boolean;
  total: number;
  refunds: RefundRow[];
};

async function pullRefunds(pageNo: number, loadFail: string): Promise<{ page: RefundPage | null; message: string }> {
  const result = await getJson(`/api/admin/refunds?page=${pageNo}&page_size=${PAGE_SIZE}`);
  if (!result.ok || !result.envelope.data) {
    return { page: null, message: errorMessage(result.envelope, loadFail) };
  }
  const data = result.envelope.data;
  return {
    page: {
      actorId: typeof data.actor_id === "string" ? data.actor_id : "",
      canRequest: data.can_request === true,
      canExecute: data.can_execute === true,
      total: typeof data.total === "number" ? data.total : 0,
      refunds: readRefunds(data.refunds),
    },
    message: "",
  };
}

export function AdminRefunds() {
  const { t } = useI18n();
  const [page, setPage] = useState<RefundPage | null>(null);
  const [pageNo, setPageNo] = useState(1);
  const { flash, setFlash } = useBootFlash(t.admin.pages.refunds.loading);
  const [busy, setBusy] = useState(false);

  async function load() {
    const next = await pullRefunds(pageNo, t.admin.pages.refunds.loadFail);
    setPage(next.page);
    setFlash(loadFlash(next.message));
  }

  useEffect(() => {
    void (async () => {
      const next = await pullRefunds(pageNo, t.admin.pages.refunds.loadFail);
      setPage(next.page);
      setFlash(loadFlash(next.message));
    })();
  }, [pageNo]);

  async function requestRefund(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    const result = await postJson("/api/admin/refunds", {
      order_no: String(form.get("order_no") ?? ""),
      destination: String(form.get("destination") ?? ""),
      reason: String(form.get("reason") ?? ""),
    });
    setBusy(false);
    setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.requested, apiErrorLabel(t, result.envelope, t.admin.pages.refunds.msg.requestFail)));
    if (result.ok) {
      formEl.reset();
      await load();
    }
  }

  async function review(id: string) {
    if (!window.confirm(t.admin.pages.refunds.msg.confirmReview)) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/refunds/${id}/review`, {});
    setBusy(false);
    setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.reviewed, apiErrorLabel(t, result.envelope, t.admin.pages.refunds.msg.reviewFail)));
    if (result.ok) {
      await load();
    }
  }

  async function reject(id: string) {
    const reason = window.prompt(t.admin.pages.refunds.rejectPrompt, "") ?? "";
    if (!window.confirm(t.admin.pages.refunds.msg.confirmReject)) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/refunds/${id}/reject`, { reason });
    setBusy(false);
    setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.rejected, apiErrorLabel(t, result.envelope, t.admin.pages.refunds.msg.rejectFail)));
    if (result.ok) {
      await load();
    }
  }

  async function execute(id: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const tx = String(new FormData(formEl).get("tx_hash") ?? "").trim();
    if (!window.confirm(t.admin.pages.refunds.msg.confirmExecute)) {
      return;
    }
    setBusy(true);
    const result = await postJson(`/api/admin/refunds/${id}/execute`, { tx_hash: tx || null });
    setBusy(false);
    setFlash(resultFlash(result.ok, t.admin.pages.refunds.msg.executed, apiErrorLabel(t, result.envelope, t.admin.pages.refunds.msg.executeFail)));
    if (result.ok) {
      formEl.reset();
      await load();
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.refunds.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.refunds.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      {page && !page.canRequest ? (
        <p className="text-sm text-foreground/70">{t.admin.pages.refunds.cannotOperate}</p>
      ) : null}
      {page?.canRequest ? (
        <form className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-2" onSubmit={(event) => void requestRefund(event)}>
          <label className="text-sm">
            {t.admin.pages.refunds.orderNo}
            <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.refunds.orderHint}</span>
            <input name="order_no" required className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
          </label>
          <label className="text-sm">
            {t.admin.pages.refunds.destination}
            <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.refunds.destinationHint}</span>
            <input
              name="destination"
              placeholder={t.admin.pages.refunds.destinationPlaceholder}
              className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2"
            />
          </label>
          <label className="text-sm sm:col-span-2">
            {t.admin.pages.refunds.reason}
            <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.refunds.reasonHint}</span>
            <input name="reason" required className="mt-1 w-full rounded border border-border bg-transparent px-3 py-2" />
          </label>
          <button type="submit" disabled={busy} className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground">
            {t.admin.actions.requestRefund}
          </button>
        </form>
      ) : null}
      {page && page.refunds.length === 0 ? <p className="text-sm text-foreground/70">{t.admin.pages.refunds.emptyAll}</p> : null}
      <ul className="space-y-3">
        {page?.refunds.map((refund) => (
          <li key={refund.id} className="space-y-2 rounded-lg border border-border p-4 text-sm">
            <p>
              {refund.order_no} · {refund.email} · {statusLabel(t, "refund", refund.status)} · {refund.amount}{" "}
              {refund.currency}
            </p>
            <p className="text-foreground/70">
              {refund.reason || t.admin.actions.none}{" "}
              {refund.destination_address ? `· ${refund.destination_address}` : ""}
            </p>
            {page.canRequest && (refund.status === "requested" || refund.status === "reviewed") && refund.requested_by !== page.actorId ? (
              <div className="flex flex-wrap gap-2">
                {refund.status === "requested" ? (
                  <button type="button" disabled={busy} className="rounded border border-border px-3 py-1" onClick={() => void review(refund.id)}>
                    {t.admin.actions.review}
                  </button>
                ) : null}
                <button type="button" disabled={busy} className="rounded border border-border px-3 py-1" onClick={() => void reject(refund.id)}>
                  {t.admin.actions.reject}
                </button>
              </div>
            ) : null}
            {page.canExecute && refund.status === "reviewed" && refund.requested_by !== page.actorId && refund.reviewed_by !== page.actorId ? (
              <form className="flex flex-wrap gap-2" onSubmit={(event) => void execute(refund.id, event)}>
                <input name="tx_hash" placeholder={t.admin.pages.refunds.txHashPlaceholder} className="rounded border border-border bg-transparent px-3 py-1" />
                <button type="submit" disabled={busy} className="rounded border border-border px-3 py-1">
                  {t.admin.actions.execute}
                </button>
              </form>
            ) : null}
          </li>
        ))}
      </ul>
      <PageControls page={pageNo} pageSize={PAGE_SIZE} total={page?.total ?? 0} onPageChange={setPageNo} />
    </section>
  );
}

function readRefunds(value: unknown): RefundRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.order_no !== "string") {
      return [];
    }
    return [
      {
        id: row.id,
        order_no: row.order_no,
        email: typeof row.email === "string" ? row.email : "",
        amount: typeof row.amount === "string" ? row.amount : "",
        currency: typeof row.currency === "string" ? row.currency : "",
        status: typeof row.status === "string" ? row.status : "",
        destination_address: typeof row.destination_address === "string" ? row.destination_address : "",
        reason: typeof row.reason === "string" ? row.reason : "",
        requested_by: typeof row.requested_by === "string" ? row.requested_by : "",
        reviewed_by: typeof row.reviewed_by === "string" ? row.reviewed_by : null,
      },
    ];
  });
}
