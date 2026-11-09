"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  loadFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { errorMessage, getJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { RefreshButton } from "@/components/ui/refresh-button";

const PAGE_SIZE = 20;

type UsageRow = {
  id: string;
  email: string;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  user_charge: string | null;
  currency: string;
  settlement_status: string;
  http_status: number | null;
};

async function pullUsage(page: number, loadFail: string): Promise<{ records: UsageRow[]; total: number; message: string }> {
  const result = await getJson(`/api/admin/usage?page=${page}&page_size=${PAGE_SIZE}`);
  if (!result.ok || !result.envelope.data) {
    return { records: [], total: 0, message: errorMessage(result.envelope, loadFail) };
  }
  return {
    records: readRecords(result.envelope.data.records),
    total: typeof result.envelope.data.total === "number" ? result.envelope.data.total : 0,
    message: "",
  };
}

export function AdminUsage() {
  const { t } = useI18n();
  const [records, setRecords] = useState<UsageRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { flash, setFlash } = useBootFlash(t.admin.pages.usage.loading);

  useEffect(() => {
    void (async () => {
      const next = await pullUsage(page, t.admin.pages.usage.loadFail);
      setRecords(next.records);
      setTotal(next.total);
      setFlash(loadFlash(next.message));
    })();
  }, [page]);

  async function load() {
    const next = await pullUsage(page, t.admin.pages.usage.loadFail);
    setRecords(next.records);
    setTotal(next.total);
    setFlash(loadFlash(next.message));
  }

  return (
    <section className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.usage.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.usage.lead}</p>
          </div>
          <RefreshButton onRefresh={load} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>
      {records.length === 0 && !flash ? <p className="text-sm text-foreground/70">{t.admin.pages.usage.emptyAll}</p> : null}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-foreground/70">
            <th className="py-2 pr-3 font-medium">{t.admin.pages.usage.customer}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.usage.model}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.usage.tokens}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.usage.charge}</th>
            <th className="py-2 font-medium">{t.admin.pages.usage.status}</th>
          </tr>
        </thead>
        <tbody>
          {records.map((row) => (
            <tr key={row.id} className="border-b border-border">
              <td className="py-2 pr-3">{row.email}</td>
              <td className="py-2 pr-3">{row.model_id || t.admin.actions.none}</td>
              <td className="py-2 pr-3">
                {row.input_tokens} / {row.output_tokens}
              </td>
              <td className="py-2 pr-3">{row.user_charge === null ? t.admin.actions.none : `${row.user_charge} ${row.currency}`}</td>
              <td className="py-2">
                {row.settlement_status}
                {row.http_status === null ? "" : ` · ${row.http_status}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

function readRecords(value: unknown): UsageRow[] {
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
        model_id: typeof row.model_id === "string" ? row.model_id : "",
        input_tokens: typeof row.input_tokens === "number" ? row.input_tokens : 0,
        output_tokens: typeof row.output_tokens === "number" ? row.output_tokens : 0,
        user_charge: typeof row.user_charge === "string" ? row.user_charge : null,
        currency: typeof row.currency === "string" ? row.currency : "",
        settlement_status: typeof row.settlement_status === "string" ? row.settlement_status : "",
        http_status: typeof row.http_status === "number" ? row.http_status : null,
      },
    ];
  });
}
