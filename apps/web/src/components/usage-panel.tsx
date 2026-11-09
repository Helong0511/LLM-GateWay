"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
  infoFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { getJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";

const PAGE_SIZE = 20;

type UsageRow = {
  id: string;
  requestId: string;
  modelId: string;
  startedAt: string;
  inputTokens: number;
  outputTokens: number;
  status: string;
  charge: string;
};

export function UsagePanel() {
  const { t } = useI18n();
  const u = t.console.usage;
  const [rows, setRows] = useState<UsageRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { flash, setFlash } = useBootFlash(t.console.usage.loading);

  useEffect(() => {
    void (async () => {
      const result = await getJson(`/api/usage?page=${page}&page_size=${PAGE_SIZE}&sort=-started_at`);
      if (!result.ok || !Array.isArray(result.envelope.data?.records)) {
        setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.usage.loadFail)));
        return;
      }
      setRows(
        result.envelope.data.records
          .map((value) => asRow(value, u.unrecorded, u.unpriced))
          .filter((item): item is UsageRow => item !== null),
      );
      setTotal(typeof result.envelope.data.total === "number" ? result.envelope.data.total : 0);
      setFlash(result.envelope.data.records.length === 0 ? infoFlash(u.empty) : null);
    })();
  }, [page, u.empty, u.unpriced, u.unrecorded]);

  return (
    <section className="max-w-4xl space-y-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{u.title}</h1>
        <p className="mt-2 text-sm text-foreground/70">{u.lead}</p>
      </header>
      {flash ? <FlashBanner flash={flash} compact className="mt-0" /> : null}
      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-border text-foreground/70">
                <th className="py-2 font-medium">{u.colTime}</th>
                <th className="py-2 font-medium">{u.colRequestId}</th>
                <th className="py-2 font-medium">{u.colModel}</th>
                <th className="py-2 font-medium">{u.colInput}</th>
                <th className="py-2 font-medium">{u.colOutput}</th>
                <th className="py-2 font-medium">{u.colStatus}</th>
                <th className="py-2 font-medium">{u.colCharge}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-border">
                  <td className="py-2 whitespace-nowrap">{row.startedAt}</td>
                  <td className="py-2 font-mono text-xs">{row.requestId}</td>
                  <td className="py-2">{row.modelId}</td>
                  <td className="py-2">{row.inputTokens}</td>
                  <td className="py-2">{row.outputTokens}</td>
                  <td className="py-2">{row.status}</td>
                  <td className="py-2">{row.charge}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

function asRow(value: unknown, unrecorded: string, unpriced: string): UsageRow | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  if (typeof row.id !== "string" || typeof row.request_id !== "string") {
    return null;
  }
  return {
    id: row.id,
    requestId: row.request_id,
    modelId: typeof row.model_id === "string" ? row.model_id : unrecorded,
    startedAt: typeof row.started_at === "string" ? row.started_at : "",
    inputTokens: typeof row.input_tokens === "number" ? row.input_tokens : 0,
    outputTokens: typeof row.output_tokens === "number" ? row.output_tokens : 0,
    status: typeof row.settlement_status === "string" ? row.settlement_status : "",
    charge: typeof row.user_charge === "string" ? row.user_charge : unpriced,
  };
}
