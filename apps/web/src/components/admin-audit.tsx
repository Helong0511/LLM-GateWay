"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
  loadFlash,
  okFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { errorMessage, getJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { RefreshButton } from "@/components/ui/refresh-button";

const PAGE_SIZE = 20;

async function pullEvents(page: number, loadFail: string): Promise<{ items: AuditRow[]; total: number; message: string }> {
  const result = await getJson(`/api/admin/audit?page=${page}&page_size=${PAGE_SIZE}`);
  if (!result.ok || !result.envelope.data) {
    return { items: [], total: 0, message: errorMessage(result.envelope, loadFail) };
  }
  return {
    items: readEvents(result.envelope.data.events),
    total: typeof result.envelope.data.total === "number" ? result.envelope.data.total : 0,
    message: "",
  };
}

type AuditRow = {
  seq: number;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  recorded_at: string;
};

export function AdminAudit() {
  const { t } = useI18n();
  const [events, setEvents] = useState<AuditRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { flash, setFlash } = useBootFlash(t.admin.pages.audit.loading);

  useEffect(() => {
    void (async () => {
      const next = await pullEvents(page, t.admin.pages.audit.loadFail);
      setEvents(next.items);
      setTotal(next.total);
      setFlash(loadFlash(next.message));
    })();
  }, [page]);

  async function load() {
    const next = await pullEvents(page, t.admin.pages.audit.loadFail);
    setEvents(next.items);
    setTotal(next.total);
    setFlash(loadFlash(next.message));
  }

  async function verify() {
    const result = await getJson("/api/admin/audit/verify");
    if (!result.ok || !result.envelope.data) {
      setFlash(errFlash(apiErrorLabel(t, result.envelope, t.admin.pages.audit.msg.verifyFail)));
      return;
    }
    const data = result.envelope.data;
    setFlash(
      data.ok === true
        ? okFlash(t.admin.pages.audit.msg.chainOk.replace("{checked}", String(data.checked)))
        : errFlash(t.admin.pages.audit.msg.chainBroken.replace("{seq}", String(data.broken_seq))),
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.audit.title}</h1>
          <p className="mt-3 text-sm text-foreground/70">{t.admin.pages.audit.lead}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded border border-border px-3 py-2 text-sm" onClick={() => void verify()}>
            {t.admin.pages.audit.verifyChain}
          </button>
          <RefreshButton onRefresh={load} />
        </div>
      </div>
      {flash ? <FlashBanner flash={flash} compact className="mt-0" /> : null}
      {events.length === 0 && !flash ? (
        <p className="text-sm text-foreground/70">{t.admin.pages.audit.emptyAll}</p>
      ) : null}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-foreground/70">
            <th className="py-2 pr-3 font-medium">{t.admin.pages.audit.seq}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.audit.action}</th>
            <th className="py-2 pr-3 font-medium">{t.admin.pages.audit.target}</th>
            <th className="py-2 font-medium">{t.admin.pages.audit.detail}</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.seq} className="border-b border-border">
              <td className="py-2 pr-3">{event.seq}</td>
              <td className="py-2 pr-3">{event.action}</td>
              <td className="py-2 pr-3">
                {event.target_type} {event.target_id}
              </td>
              <td className="py-2">{event.detail || t.admin.actions.none}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}

function readEvents(value: unknown): AuditRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.seq !== "number" || typeof row.action !== "string") {
      return [];
    }
    return [
      {
        seq: row.seq,
        action: row.action,
        target_type: typeof row.target_type === "string" ? row.target_type : "",
        target_id: typeof row.target_id === "string" ? row.target_id : "",
        detail: typeof row.detail === "string" ? row.detail : "",
        recorded_at: typeof row.recorded_at === "string" ? row.recorded_at : "",
      },
    ];
  });
}
