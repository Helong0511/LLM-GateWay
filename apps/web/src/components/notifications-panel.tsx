"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import {
  FlashBanner,
  infoFlash,
  loadFlash,
  resultFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { PageControls } from "@/components/page-controls";
import { Button } from "@/components/ui/button";
import { errorMessage, getJson, patchJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { balanceReasonLabel, notificationBody, notificationTitle } from "@/lib/notify-label";

const PAGE_SIZE = 20;

type Note = { id: string; title: string; body: string; read: boolean };

type Snapshot = {
  notes: Note[];
  total: number;
  /** 信息码或错误文案；空串表示无提示 */
  message: string;
  messageKind: "info" | "error" | "";
  alertsEnabled: boolean;
  warnHigh: string;
  warnLow: string;
};

async function pullNotifications(
  page: number,
  copy: { balanceSkipped: string; loadFail: string },
): Promise<Snapshot> {
  const refreshed = await postJson("/api/notifications/refresh", {});
  let alertsEnabled = true;
  let warnHigh = "10";
  let warnLow = "2";
  let message = "";
  let messageKind: Snapshot["messageKind"] = "";
  if (refreshed.ok && refreshed.envelope.data) {
    const data = refreshed.envelope.data;
    if (typeof data.warn_high === "string") {
      warnHigh = data.warn_high;
    }
    if (typeof data.warn_low === "string") {
      warnLow = data.warn_low;
    }
    if (typeof data.balance_alerts_enabled === "boolean") {
      alertsEnabled = data.balance_alerts_enabled;
    }
    if (typeof data.balance_reason === "string" && data.balance_reason) {
      message = data.balance_reason;
      messageKind = "info";
    } else if (data.balance_alerts === "skipped") {
      message = copy.balanceSkipped;
      messageKind = "info";
    }
  }
  const result = await getJson(`/api/notifications?page=${page}&page_size=${PAGE_SIZE}`);
  if (!result.ok || !Array.isArray(result.envelope.data?.notifications)) {
    return {
      notes: [],
      total: 0,
      message: errorMessage(result.envelope, copy.loadFail),
      messageKind: "error",
      alertsEnabled,
      warnHigh,
      warnLow,
    };
  }
  return {
    notes: result.envelope.data.notifications
      .map((item) => {
        if (!item || typeof item !== "object") {
          return null;
        }
        const row = item as Record<string, unknown>;
        if (typeof row.id !== "string" || typeof row.title !== "string") {
          return null;
        }
        return {
          id: row.id,
          title: row.title,
          body: typeof row.body === "string" ? row.body : "",
          read: typeof row.read_at === "string",
        };
      })
      .filter((item): item is Note => item !== null),
    total: typeof result.envelope.data.total === "number" ? result.envelope.data.total : 0,
    message,
    messageKind,
    alertsEnabled,
    warnHigh,
    warnLow,
  };
}

export function NotificationsPanel() {
  const { t } = useI18n();
  const n = t.console.notifications;
  const [notes, setNotes] = useState<Note[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [flash, setFlash] = useState<FlashMessage | null>(infoFlash(n.loading));
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [warnHigh, setWarnHigh] = useState("10");
  const [warnLow, setWarnLow] = useState("2");

  const pullCopy = { balanceSkipped: n.balanceSkipped, loadFail: n.loadFail };

  useEffect(() => {
    void (async () => {
      const next = await pullNotifications(page, pullCopy);
      setNotes(next.notes);
      setTotal(next.total);
      if (next.messageKind === "error") {
        setFlash(loadFlash(next.message));
      } else if (next.messageKind === "info" && next.message) {
        const text =
          next.message === n.balanceSkipped ? next.message : balanceReasonLabel(t, next.message);
        setFlash(infoFlash(text));
      } else {
        setFlash(null);
      }
      setAlertsEnabled(next.alertsEnabled);
      setWarnHigh(next.warnHigh);
      setWarnLow(next.warnLow);
    })();
  }, [page, n.balanceSkipped, n.loadFail, t]);

  async function savePreference(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await patchJson("/api/notifications/preferences", {
      balance_alerts_enabled: alertsEnabled,
      warn_high: warnHigh,
      warn_low: warnLow,
    });
    setFlash(resultFlash(result.ok, n.saveAlerts, apiErrorLabel(t, result.envelope, n.loadFail)));
  }

  async function markRead(id: string) {
    const result = await postJson(`/api/notifications/${id}/read`, {});
    setFlash(resultFlash(result.ok, n.markRead, apiErrorLabel(t, result.envelope, n.loadFail)));
    if (result.ok) {
      const next = await pullNotifications(page, pullCopy);
      setNotes(next.notes);
      setTotal(next.total);
      setAlertsEnabled(next.alertsEnabled);
      setWarnHigh(next.warnHigh);
      setWarnLow(next.warnLow);
    }
  }

  return (
    <section className="max-w-2xl space-y-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{n.title}</h1>
        <p className="mt-2 text-sm text-foreground/70">{n.lead}</p>
      </header>
      <form className="space-y-3 rounded-md border border-border p-4 text-sm" onSubmit={(event) => void savePreference(event)}>
        <h2 className="text-lg font-medium">{n.balanceAlerts}</h2>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={alertsEnabled} onChange={(event) => setAlertsEnabled(event.target.checked)} />
          {n.enableAlerts}
        </label>
        <label className="block">
          {n.warnHigh}
          <input
            value={warnHigh}
            onChange={(event) => setWarnHigh(event.target.value)}
            className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2"
          />
        </label>
        <label className="block">
          {n.warnLow}
          <input
            value={warnLow}
            onChange={(event) => setWarnLow(event.target.value)}
            className="mt-1 w-full rounded-md border border-border bg-transparent px-3 py-2"
          />
        </label>
        <Button type="submit">{n.saveAlerts}</Button>
      </form>
      {flash ? <FlashBanner flash={flash} compact className="mt-0" /> : null}
      {notes.length === 0 ? <p className="text-sm text-foreground/70">{n.empty}</p> : null}
      <ul className="space-y-3">
        {notes.map((item) => (
          <li key={item.id} className="rounded-md border border-border px-3 py-3 text-sm">
            <p className="font-medium">{notificationTitle(t, item.title)}</p>
            <p className="mt-1 text-foreground/70">{notificationBody(t, item.title, item.body)}</p>
            {item.read ? (
              <p className="mt-2 text-foreground/60">{n.read}</p>
            ) : (
              <Button className="mt-2" type="button" variant="outline" size="sm" onClick={() => void markRead(item.id)}>
                {n.markRead}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <PageControls page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
    </section>
  );
}
