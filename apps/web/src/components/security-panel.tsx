"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlashFromApiSecurity,
  loadFlash,
  resultSecurityFlash,
  securityFlash,
} from "@/components/ui/flash";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { deleteJson, getJson, postJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";
import type { Messages } from "@/content/messages";

type SessionRow = { id: string; current: boolean; agent: string; seen: string };
type DeviceRow = { id: string; agent: string; ip: string; seen: string };

type SecuritySnapshot = {
  sessions: SessionRow[];
  devices: DeviceRow[];
  totpEnabled: boolean | null;
  message: string;
};

async function pullSecurity(t: Messages): Promise<SecuritySnapshot> {
  const loadFail = t.console.security.loadFail;
  const [sessionResult, deviceResult, meResult] = await Promise.all([
    getJson("/api/auth/sessions"),
    getJson("/api/auth/devices"),
    getJson("/api/auth/me"),
  ]);
  if (!sessionResult.ok || !deviceResult.ok) {
    const envelope = !sessionResult.ok ? sessionResult.envelope : deviceResult.envelope;
    return {
      sessions: [],
      devices: [],
      totpEnabled: null,
      message: apiErrorLabel(t, envelope, loadFail),
    };
  }
  const sessionRows = Array.isArray(sessionResult.envelope.data?.sessions) ? sessionResult.envelope.data.sessions : [];
  const deviceRows = Array.isArray(deviceResult.envelope.data?.devices) ? deviceResult.envelope.data.devices : [];
  const sessions = sessionRows
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      if (typeof row.id !== "string") {
        return null;
      }
      return {
        id: row.id,
        current: row.current === true,
        agent: typeof row.user_agent === "string" ? row.user_agent : "",
        seen: typeof row.last_seen_at === "string" ? row.last_seen_at : "",
      };
    })
    .filter((item): item is SessionRow => item !== null);
  const devices = deviceRows
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      if (typeof row.id !== "string") {
        return null;
      }
      return {
        id: row.id,
        agent: typeof row.user_agent === "string" ? row.user_agent : "",
        ip: typeof row.ip === "string" ? row.ip : "",
        seen: typeof row.last_seen_at === "string" ? row.last_seen_at : "",
      };
    })
    .filter((item): item is DeviceRow => item !== null);
  let totpEnabled: boolean | null = null;
  const user = meResult.envelope.data?.user;
  if (user && typeof user === "object" && "totp_enabled" in user) {
    totpEnabled = (user as { totp_enabled?: unknown }).totp_enabled === true;
  }
  return { sessions, devices, totpEnabled, message: "" };
}

export function SecurityPanel() {
  const { t } = useI18n();
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [devices, setDevices] = useState<DeviceRow[]>([]);
  const { flash, setFlash } = useBootFlash(t.console.security.loading);
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [emailToken, setEmailToken] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [totpEnabled, setTotpEnabled] = useState(false);

  function apply(next: SecuritySnapshot) {
    setSessions(next.sessions);
    setDevices(next.devices);
    if (next.totpEnabled !== null) {
      setTotpEnabled(next.totpEnabled);
    }
    setFlash(loadFlash(next.message));
  }

  async function load() {
    apply(await pullSecurity(t));
  }

  useEffect(() => {
    void (async () => {
      apply(await pullSecurity(t));
    })();
  }, []);

  async function revoke(id: string) {
    const result = await deleteJson(`/api/auth/sessions/${id}`);
    setFlash(resultSecurityFlash(result.ok, "sessionEnded", result.envelope, "sessionEndFail"));
    if (result.ok) {
      await load();
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    const result = await postJson("/api/auth/change-password", {
      current_password: currentPassword,
      password,
    });
    setFlash(resultSecurityFlash(result.ok, "passwordChanged", result.envelope, "passwordFail"));
    if (result.ok) {
      setCurrentPassword("");
      setPassword("");
    }
  }

  async function requestEmail(event: FormEvent) {
    event.preventDefault();
    const result = await postJson("/api/auth/email-change", { password: emailPassword, new_email: newEmail });
    if (!result.ok) {
      setFlash(errFlashFromApiSecurity(result.envelope, "emailRequestFail"));
      return;
    }
    const delivery = result.envelope.data?.email_delivery;
    setFlash(
      delivery === "unconfigured"
        ? securityFlash("warning", "mailNotConfigured")
        : securityFlash("success", "mailQueued"),
    );
  }

  async function confirmEmail(event: FormEvent) {
    event.preventDefault();
    const result = await postJson("/api/auth/email-change/confirm", { token: emailToken });
    setFlash(resultSecurityFlash(result.ok, "emailChanged", result.envelope, "emailConfirmFail"));
    if (result.ok) {
      router.refresh();
    }
  }

  async function setupTotp() {
    const result = await postJson("/api/auth/totp/setup", {});
    if (!result.ok || typeof result.envelope.data?.secret !== "string") {
      setFlash(errFlashFromApiSecurity(result.envelope, "totpPrepareFail"));
      return;
    }
    setTotpSecret(result.envelope.data.secret);
    setFlash(securityFlash("warning", "totpSaveSeed"));
  }

  async function enableTotp(event: FormEvent) {
    event.preventDefault();
    const result = await postJson("/api/auth/totp/enable", { code: totpCode });
    if (!result.ok || !Array.isArray(result.envelope.data?.recovery_codes)) {
      setFlash(errFlashFromApiSecurity(result.envelope, "totpEnableFail"));
      return;
    }
    setRecoveryCodes(result.envelope.data.recovery_codes.filter((item): item is string => typeof item === "string"));
    setTotpSecret("");
    setTotpEnabled(true);
    setFlash(securityFlash("success", "totpEnabled"));
  }

  async function disableTotp(event: FormEvent) {
    event.preventDefault();
    const result = await postJson("/api/auth/totp/disable", {
      password: disablePassword,
      code: disableCode,
    });
    setFlash(resultSecurityFlash(result.ok, "totpDisabled", result.envelope, "totpDisableFail"));
    if (result.ok) {
      setTotpEnabled(false);
      setDisablePassword("");
      setDisableCode("");
      setRecoveryCodes([]);
    }
  }

  const s = t.console.security;

  return (
    <section className="max-w-3xl space-y-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{s.title}</h1>
        <p className="mt-2 text-sm text-foreground/70">{s.lead}</p>
      </header>
      {flash ? <FlashBanner flash={flash} compact className="mt-0" /> : null}

      <form className="space-y-3 rounded-lg border border-border bg-card/60 p-4" onSubmit={changePassword}>
        <h2 className="text-lg font-medium">{s.changePassword}</h2>
        <input
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          type="password"
          placeholder={s.currentPassword}
          value={currentPassword}
          onChange={(event) => setCurrentPassword(event.target.value)}
          required
          autoComplete="current-password"
        />
        <input
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          type="password"
          placeholder={s.newPassword}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          autoComplete="new-password"
        />
        <Button type="submit">{s.savePassword}</Button>
      </form>

      <div className="space-y-3 rounded-lg border border-border bg-card/60 p-4">
        <h2 className="text-lg font-medium">{s.changeEmail}</h2>
        <p className="text-xs text-foreground/60">{s.emailHint}</p>
        <form className="space-y-3" onSubmit={requestEmail}>
          <input
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            type="password"
            placeholder={s.currentPassword}
            value={emailPassword}
            onChange={(event) => setEmailPassword(event.target.value)}
            required
            autoComplete="current-password"
          />
          <input
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            type="email"
            placeholder={s.newEmail}
            value={newEmail}
            onChange={(event) => setNewEmail(event.target.value)}
            required
          />
          <Button type="submit">{s.sendConfirmEmail}</Button>
        </form>
        <form className="space-y-3" onSubmit={confirmEmail}>
          <input
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            placeholder={s.emailToken}
            value={emailToken}
            onChange={(event) => setEmailToken(event.target.value)}
            required
          />
          <Button type="submit" variant="outline">
            {s.confirmEmail}
          </Button>
        </form>
      </div>

      <div className="space-y-3 rounded-lg border border-border bg-card/60 p-4">
        <h2 className="text-lg font-medium">{s.totp}</h2>
        <p className="text-sm text-foreground/70">{totpEnabled ? s.totpOn : s.totpOff}</p>
        {!totpEnabled ? (
          <>
            <Button type="button" variant="outline" onClick={() => void setupTotp()}>
              {s.generateSeed}
            </Button>
            {totpSecret ? (
              <p className="break-all font-mono text-sm">
                {s.seedLabel}
                {totpSecret}
              </p>
            ) : null}
            <form className="space-y-3" onSubmit={enableTotp}>
              <input
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder={s.totpCode}
                value={totpCode}
                onChange={(event) => setTotpCode(event.target.value)}
                required
                autoComplete="one-time-code"
              />
              <Button type="submit">{s.enableTotp}</Button>
            </form>
          </>
        ) : (
          <form className="space-y-3" onSubmit={disableTotp}>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              type="password"
              placeholder={s.currentPassword}
              value={disablePassword}
              onChange={(event) => setDisablePassword(event.target.value)}
              required
              autoComplete="current-password"
            />
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder={s.totpOrRecovery}
              value={disableCode}
              onChange={(event) => setDisableCode(event.target.value)}
              required
              autoComplete="one-time-code"
            />
            <Button type="submit" variant="outline">
              {s.disableTotp}
            </Button>
          </form>
        )}
        {recoveryCodes.length > 0 ? (
          <ul className="space-y-1 font-mono text-sm">
            {recoveryCodes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <div>
        <h2 className="text-lg font-medium">{s.sessions}</h2>
        <p className="mt-1 text-xs text-foreground/60">{s.sessionHint}</p>
        <ul className="mt-2 space-y-2 text-sm">
          {sessions.length === 0 ? <li className="text-foreground/60">{s.noSessions}</li> : null}
          {sessions.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
              <span>
                {item.current ? s.currentSession : s.otherSession} · {item.agent || s.unknownClient} · {item.seen}
              </span>
              {item.current ? null : (
                <Button type="button" variant="outline" size="sm" onClick={() => void revoke(item.id)}>
                  {t.shell.logout}
                </Button>
              )}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h2 className="text-lg font-medium">{s.devices}</h2>
        <ul className="mt-2 space-y-2 text-sm">
          {devices.length === 0 ? <li className="text-foreground/60">{s.noDevices}</li> : null}
          {devices.map((item) => (
            <li key={item.id} className="rounded-md border border-border px-3 py-2">
              {item.agent || s.unknownClient} · {item.ip || s.unknownIp} · {item.seen}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
