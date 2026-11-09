"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

import {
  FlashBanner,
  deliveryFlash,
  errFlashFromApi,
  type FlashMessage,
} from "@/components/ui/flash";

import { useI18n } from "@/components/locale-provider";
import { Button } from "@/components/ui/button";
import { getJson, postJson } from "@/lib/api-client";
import { postLoginPath } from "@/lib/guard";

function Field({
  label,
  type,
  value,
  onChange,
  autoComplete,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
}) {
  return (
    <label className="block text-sm">
      <span>{label}</span>
      <input
        className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2"
        type={type}
        value={value}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}

export function LoginForm() {
  const { t } = useI18n();
  const copy = t.auth;
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [pending, setPending] = useState(false);

  async function finishLogin() {
    const me = await getJson("/api/auth/me");
    if (!me.ok) {
      setFlash(errFlashFromApi(me.envelope, copy.loginFailed));
      return;
    }
    router.push(postLoginPath(params.get("next"), me.envelope.data?.roles));
    router.refresh();
  }

  async function onLogin(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const result = await postJson("/api/auth/login", { email, password });
    if (!result.ok) {
      setPending(false);
      setFlash(errFlashFromApi(result.envelope, copy.loginFailed));
      return;
    }
    if (result.envelope.data?.totp_required === true && typeof result.envelope.data.challenge === "string") {
      setPending(false);
      setChallenge(result.envelope.data.challenge);
      setFlash({ level: "info", authCopy: "totpHint" });
      return;
    }
    await finishLogin();
    setPending(false);
  }

  async function onTotp(event: FormEvent) {
    event.preventDefault();
    if (!challenge) {
      return;
    }
    setPending(true);
    const result = await postJson("/api/auth/totp/verify", { challenge, code });
    if (!result.ok) {
      setPending(false);
      setFlash(errFlashFromApi(result.envelope, copy.totpFailed));
      return;
    }
    await finishLogin();
    setPending(false);
  }

  return (
    <section className="max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight">{copy.loginTitle}</h1>
      <p className="mt-2 text-sm text-foreground/70">{copy.loginLead}</p>
      <form className="mt-6 space-y-4" onSubmit={challenge ? onTotp : onLogin}>
        {challenge ? (
          <Field label={copy.totpLabel} type="text" value={code} onChange={setCode} autoComplete="one-time-code" />
        ) : (
          <>
            <Field label={copy.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
            <Field label={copy.password} type="password" value={password} onChange={setPassword} autoComplete="current-password" />
          </>
        )}
        {flash ? <FlashBanner flash={flash} compact /> : null}
        <Button type="submit" disabled={pending}>
          {pending ? copy.submitting : challenge ? copy.totpSubmit : copy.loginTitle}
        </Button>
      </form>
      <p className="mt-4 text-sm">
        <Link href="/forgot-password">{copy.forgot}</Link>
        <span className="px-2 text-foreground/40">/</span>
        <Link href="/register">{copy.register}</Link>
      </p>
    </section>
  );
}

export function RegisterForm() {
  const { t } = useI18n();
  const copy = t.auth;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const result = await postJson("/api/auth/register", {
      email,
      password,
      accept_terms: acceptTerms,
      accept_privacy: acceptPrivacy,
    });
    setPending(false);
    if (!result.ok) {
      setFlash(errFlashFromApi(result.envelope, copy.registerFailed));
      return;
    }
    setFlash(deliveryFlash(result.envelope.data?.email_delivery));
  }

  return (
    <section className="max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight">{copy.registerTitle}</h1>
      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <Field label={copy.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field label={copy.password} type="password" value={password} onChange={setPassword} autoComplete="new-password" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={acceptTerms} onChange={(event) => setAcceptTerms(event.target.checked)} />
          {copy.agreeTerms} <Link href="/terms">{copy.terms}</Link>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={acceptPrivacy} onChange={(event) => setAcceptPrivacy(event.target.checked)} />
          {copy.agreePrivacy} <Link href="/privacy">{copy.privacy}</Link>
        </label>
        {flash ? <FlashBanner flash={flash} compact /> : null}
        <Button type="submit" disabled={pending}>
          {pending ? copy.submitting : copy.register}
        </Button>
      </form>
      <p className="mt-4 text-sm">
        {copy.verifyHint} <Link href="/verify-email">{copy.verifyLink}</Link>
      </p>
    </section>
  );
}

export function ForgotForm() {
  const { t } = useI18n();
  const copy = t.auth;
  const [email, setEmail] = useState("");
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const result = await postJson("/api/auth/forgot-password", { email });
    setPending(false);
    if (!result.ok) {
      setFlash(errFlashFromApi(result.envelope, copy.forgotFailed));
      return;
    }
    setFlash(deliveryFlash(result.envelope.data?.email_delivery));
  }

  return (
    <section className="max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight">{copy.forgotTitle}</h1>
      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <Field label={copy.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
        {flash ? <FlashBanner flash={flash} compact /> : null}
        <Button type="submit" disabled={pending}>
          {pending ? copy.submitting : copy.sendReset}
        </Button>
      </form>
    </section>
  );
}

export function ResetForm() {
  const { t } = useI18n();
  const copy = t.auth;
  const params = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [token, setToken] = useState(params.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const result = await postJson("/api/auth/reset-password", { email, token, password });
    setPending(false);
    setFlash(
      result.ok
        ? { level: "success", authCopy: "resetOk" }
        : errFlashFromApi(result.envelope, copy.resetFailed),
    );
  }

  return (
    <section className="max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight">{copy.resetTitle}</h1>
      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <Field label={copy.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field label={copy.resetToken} type="text" value={token} onChange={setToken} autoComplete="off" />
        <Field label={copy.newPassword} type="password" value={password} onChange={setPassword} autoComplete="new-password" />
        {flash ? <FlashBanner flash={flash} compact /> : null}
        <Button type="submit" disabled={pending}>
          {pending ? copy.submitting : copy.resetSubmit}
        </Button>
      </form>
    </section>
  );
}

export function VerifyForm() {
  const { t } = useI18n();
  const copy = t.auth;
  const params = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [token, setToken] = useState(params.get("token") ?? "");
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const result = await postJson("/api/auth/verify-email", { email, token });
    setPending(false);
    setFlash(
      result.ok
        ? { level: "success", authCopy: "verifyOk" }
        : errFlashFromApi(result.envelope, copy.verifyFailed),
    );
  }

  async function resend() {
    setPending(true);
    const result = await postJson("/api/auth/resend-verification", { email });
    setPending(false);
    if (!result.ok) {
      setFlash(errFlashFromApi(result.envelope, copy.resendFailed));
      return;
    }
    setFlash(deliveryFlash(result.envelope.data?.email_delivery));
  }

  return (
    <section className="max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight">{copy.verifyTitle}</h1>
      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <Field label={copy.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field label={copy.verifyToken} type="text" value={token} onChange={setToken} autoComplete="off" />
        {flash ? <FlashBanner flash={flash} compact /> : null}
        <div className="flex gap-3">
          <Button type="submit" disabled={pending}>
            {pending ? copy.submitting : copy.verify}
          </Button>
          <Button type="button" variant="outline" disabled={pending || !email} onClick={() => void resend()}>
            {copy.resend}
          </Button>
        </div>
      </form>
    </section>
  );
}
