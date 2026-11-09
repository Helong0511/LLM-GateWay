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
import { Field } from "@/components/ui/field";
import { PageControls } from "@/components/page-controls";
import { RefreshButton } from "@/components/ui/refresh-button";

import { errorMessage, deleteJson, getJson, patchJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import { statusLabel } from "@/lib/status-label";

const PAGE_SIZE = 20;

type Intent = {
  orderNo: string;
  email: string;
  address: string;
  network: string;
  tailAmount: string;
  tailStatus: string;
  expiresAt: string;
};

type Blocked = {
  id: string;
  address: string;
  addressMasked: string;
  network: string;
  source: string;
  reason: string;
  createdAt: string;
};

async function pullCrypto(params: {
  intentPage: number;
  sanctionPage: number;
  q: string;
}, loadFail: string): Promise<{
  intents: Intent[];
  intentTotal: number;
  blocked: Blocked[];
  sanctionTotal: number;
  networks: string[];
  message: string;
}> {
  const query = new URLSearchParams({
    page: String(params.intentPage),
    page_size: String(PAGE_SIZE),
    sanctioned_page: String(params.sanctionPage),
    sanctioned_page_size: String(PAGE_SIZE),
  });
  if (params.q.trim()) {
    query.set("q", params.q.trim());
  }
  const result = await getJson(`/api/admin/crypto?${query.toString()}`);
  if (!result.ok || !result.envelope.data) {
    return {
      intents: [],
      intentTotal: 0,
      blocked: [],
      sanctionTotal: 0,
      networks: ["TRC20", "ERC20"],
      message: errorMessage(result.envelope, loadFail),
    };
  }
  const data = result.envelope.data;
  return {
    intents: readIntents(data.intents),
    intentTotal: typeof data.total === "number" ? data.total : 0,
    blocked: readBlocked(data.sanctioned),
    sanctionTotal: typeof data.sanctioned_total === "number" ? data.sanctioned_total : 0,
    networks: Array.isArray(data.networks)
      ? data.networks.filter((item): item is string => typeof item === "string")
      : ["TRC20", "ERC20"],
    message: "",
  };
}

export function AdminCrypto() {
  const { t, locale } = useI18n();
  const [intents, setIntents] = useState<Intent[]>([]);
  const [intentTotal, setIntentTotal] = useState(0);
  const [intentPage, setIntentPage] = useState(1);
  const [blocked, setBlocked] = useState<Blocked[]>([]);
  const [sanctionTotal, setSanctionTotal] = useState(0);
  const [sanctionPage, setSanctionPage] = useState(1);
  const [networks, setNetworks] = useState<string[]>(["TRC20", "ERC20"]);
  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const { flash, setFlash } = useBootFlash(t.admin.pages.crypto.loading);
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [showFull, setShowFull] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const data = await pullCrypto({ intentPage, sanctionPage, q: appliedQ }, t.admin.pages.crypto.loadFail);
      if (cancelled) {
        return;
      }
      setIntents(data.intents);
      setIntentTotal(data.intentTotal);
      setBlocked(data.blocked);
      setSanctionTotal(data.sanctionTotal);
      setNetworks(data.networks.length > 0 ? data.networks : ["TRC20", "ERC20"]);
      setFlash(loadFlash(data.message));
    })();
    return () => {
      cancelled = true;
    };
  }, [intentPage, sanctionPage, appliedQ]);

  async function reload() {
    const data = await pullCrypto({ intentPage, sanctionPage, q: appliedQ }, t.admin.pages.crypto.loadFail);
    setIntents(data.intents);
    setIntentTotal(data.intentTotal);
    setBlocked(data.blocked);
    setSanctionTotal(data.sanctionTotal);
    setNetworks(data.networks.length > 0 ? data.networks : ["TRC20", "ERC20"]);
    setFlash(loadFlash(data.message));
  }

  async function createSanction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    const result = await postJson("/api/admin/crypto/sanctions", {
      address: String(form.get("address") || "").trim(),
      network: String(form.get("network") || "TRC20"),
      source: String(form.get("source") || "").trim(),
      reason: String(form.get("reason") || "").trim(),
    });
    setBusy(false);
    const m = t.admin.pages.crypto.msg;
    setFlash(resultFlash(result.ok, m.created, apiErrorLabel(t, result.envelope, m.createFail)));
    if (result.ok) {
      formEl.reset();
      if (sanctionPage === 1 && appliedQ === "") {
        await reload();
      } else {
        setAppliedQ("");
        setSanctionPage(1);
      }
    }
  }

  async function saveEdit(item: Blocked, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    const result = await patchJson(`/api/admin/crypto/sanctions/${item.id}`, {
      source: String(form.get("source") || "").trim(),
      reason: String(form.get("reason") || "").trim(),
    });
    setBusy(false);
    const m = t.admin.pages.crypto.msg;
    setFlash(resultFlash(result.ok, m.updated, apiErrorLabel(t, result.envelope, m.updateFail)));
    if (result.ok) {
      setEditingId("");
      await reload();
    }
  }

  async function removeSanction(item: Blocked) {
    const m = t.admin.pages.crypto.msg;
    if (
      !window.confirm(
        m.confirmRemove.replace("{network}", item.network).replace("{address}", item.address),
      )
    ) {
      return;
    }
    setBusy(true);
    const result = await deleteJson(`/api/admin/crypto/sanctions/${item.id}`);
    setBusy(false);
    setFlash(resultFlash(result.ok, m.removed, apiErrorLabel(t, result.envelope, m.removeFail)));
    if (result.ok) {
      if (editingId === item.id) {
        setEditingId("");
      }
      await reload();
    }
  }

  return (
    <section className="space-y-8">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t.admin.pages.crypto.title}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-foreground/70">{t.admin.pages.crypto.lead}</p>
          </div>
          <RefreshButton onRefresh={reload} />
        </div>
        {flash ? <FlashBanner flash={flash} /> : null}
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-medium">{t.admin.pages.crypto.tails}</h2>
        {intents.length === 0 ? (
          <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-foreground/70">
            {t.admin.pages.crypto.emptyActive}
          </p>
        ) : null}
        <ul className="space-y-2 text-sm">
          {intents.map((row) => (
            <li key={`${row.orderNo}-${row.address}-${row.tailAmount}`} className="rounded-md border border-border px-3 py-2">
              <p>
                {row.orderNo} · {row.email} · {row.network} · {row.address}
              </p>
              <p className="mt-1 text-foreground/65">
                {t.admin.pages.crypto.tailAmount} {row.tailAmount} · {statusLabel(t, "tail", row.tailStatus)}
                {row.expiresAt ? ` · ${t.admin.pages.crypto.expires} ${formatWhen(row.expiresAt, locale)}` : ""}
              </p>
            </li>
          ))}
        </ul>
        <PageControls page={intentPage} pageSize={PAGE_SIZE} total={intentTotal} onPageChange={setIntentPage} />
      </div>

      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-medium">{t.admin.pages.crypto.sanctions}</h2>
          <p className="mt-1 text-sm text-foreground/65">{t.admin.pages.crypto.sanctionsLead}</p>
        </div>

        <form className="grid max-w-2xl gap-3 rounded-md border border-border p-4 text-sm" onSubmit={(event) => void createSanction(event)}>
          <Field label={t.admin.pages.crypto.address} hint={t.admin.pages.crypto.addressHint}>
            <input
              name="address"
              required
              placeholder={t.admin.pages.crypto.addressPlaceholder}
              className="rounded border border-border bg-background px-3 py-2 font-mono"
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
          <Field label={t.admin.pages.crypto.network} hint={t.admin.pages.crypto.networkHint}>
            <select name="network" defaultValue="TRC20" className="rounded border border-border bg-background px-3 py-2 text-foreground">
              {networks.map((net) => (
                <option key={net} value={net}>
                  {net}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t.admin.pages.crypto.source} hint={t.admin.pages.crypto.sourceHint}>
            <input name="source" required placeholder={t.admin.pages.crypto.sourcePlaceholder} className="rounded border border-border bg-background px-3 py-2" />
          </Field>
          <Field label={t.admin.pages.crypto.reason} hint={t.admin.pages.crypto.reasonHint}>
            <input name="reason" placeholder={t.admin.pages.crypto.reasonPlaceholder} className="rounded border border-border bg-background px-3 py-2" />
          </Field>
          <button type="submit" disabled={busy} className="w-fit rounded bg-foreground px-4 py-2 text-background">
            {t.admin.actions.addSanction}
          </button>
        </form>

        <form
          className="flex flex-wrap items-end gap-2 text-sm"
          onSubmit={(event) => {
            event.preventDefault();
            setSanctionPage(1);
            setAppliedQ(q);
          }}
        >
          <label>
            {t.admin.actions.search}
            <span className="mt-0.5 block text-xs text-foreground/60">{t.admin.pages.crypto.searchHint}</span>
            <input
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder={t.admin.pages.crypto.searchPlaceholder}
              className="mt-1 block min-w-56 rounded border border-border bg-background px-3 py-2"
            />
          </label>
          <button type="submit" className="rounded border border-border px-3 py-2">
            {t.admin.actions.query}
          </button>
          {appliedQ ? (
            <button
              type="button"
              className="rounded border border-border px-3 py-2"
              onClick={() => {
                setQ("");
                setSanctionPage(1);
                setAppliedQ("");
              }}
            >
              {t.admin.actions.clear}
            </button>
          ) : null}
        </form>

        {blocked.length === 0 ? (
          <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-foreground/70">
            {appliedQ ? t.admin.pages.crypto.emptyDisabled : t.admin.pages.crypto.emptyAll}
          </p>
        ) : null}
        <ul className="space-y-3 text-sm">
          {blocked.map((row) => {
            const expanded = showFull[row.id] === true;
            const display = expanded ? row.address : row.addressMasked || row.address;
            return (
              <li key={row.id} className="space-y-2 rounded-md border border-border px-3 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <p className="font-medium">
                      {row.network} ·{" "}
                      <span className="font-mono break-all">{display}</span>
                    </p>
                    <p className="text-foreground/70">
                      {t.admin.pages.crypto.source} {row.source || t.admin.actions.none}
                      {row.reason ? ` · ${row.reason}` : ""} · {t.admin.pages.crypto.recorded}{" "}
                      {formatWhen(row.createdAt, locale)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded border border-border px-3 py-1"
                      onClick={() => setShowFull((prev) => ({ ...prev, [row.id]: !expanded }))}
                    >
                      {expanded ? t.admin.actions.hideAddress : t.admin.actions.showAddress}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded border border-border px-3 py-1"
                      onClick={() => setEditingId(editingId === row.id ? "" : row.id)}
                    >
                      {editingId === row.id ? t.admin.actions.collapse : t.admin.actions.edit}
                    </button>
                    <button type="button" disabled={busy} className="rounded border border-border px-3 py-1" onClick={() => void removeSanction(row)}>
                      {t.admin.actions.remove}
                    </button>
                  </div>
                </div>
                {editingId === row.id ? (
                  <form className="grid max-w-xl gap-2 border-t border-border pt-3" onSubmit={(event) => void saveEdit(row, event)}>
                    <Field label={t.admin.pages.crypto.source}>
                      <input name="source" required defaultValue={row.source} className="rounded border border-border bg-background px-3 py-2" />
                    </Field>
                    <Field label={t.admin.pages.crypto.reason}>
                      <input name="reason" defaultValue={row.reason} className="rounded border border-border bg-background px-3 py-2" />
                    </Field>
                    <p className="text-xs text-foreground/55">{t.admin.pages.crypto.addressNetworkFixed}</p>
                    <button type="submit" disabled={busy} className="w-fit rounded bg-foreground px-3 py-1.5 text-background">
                      {t.admin.actions.save}
                    </button>
                  </form>
                ) : null}
              </li>
            );
          })}
        </ul>
        <PageControls page={sanctionPage} pageSize={PAGE_SIZE} total={sanctionTotal} onPageChange={setSanctionPage} />
      </div>
    </section>
  );
}

function formatWhen(value: string, locale: string): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(locale, { hour12: false });
}

function readIntents(value: unknown): Intent[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.order_no !== "string") {
      return [];
    }
    return [
      {
        orderNo: row.order_no,
        email: typeof row.email === "string" ? row.email : "",
        address: typeof row.address === "string" ? row.address : "",
        network: typeof row.network === "string" ? row.network : "",
        tailAmount: typeof row.tail_amount === "string" ? row.tail_amount : "",
        tailStatus: typeof row.tail_status === "string" ? row.tail_status : "",
        expiresAt: typeof row.expires_at === "string" ? row.expires_at : "",
      },
    ];
  });
}

function readBlocked(value: unknown): Blocked[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
    if (typeof row.address !== "string") {
      return [];
    }
    return [
      {
        id: typeof row.id === "string" ? row.id : `${row.network}-${row.address}`,
        address: row.address,
        addressMasked: typeof row.address_masked === "string" ? row.address_masked : row.address,
        network: typeof row.network === "string" ? row.network : "",
        source: typeof row.source === "string" ? row.source : "",
        reason: typeof row.reason === "string" ? row.reason : "",
        createdAt: typeof row.created_at === "string" ? row.created_at : "",
      },
    ];
  });
}
