"use client";

import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { useBootFlash } from "@/lib/boot-flash";
import {
  FlashBanner,
  errFlash,
    resultFlash,
  type FlashMessage,
} from "@/components/ui/flash";

import { Button } from "@/components/ui/button";
import { getJson, patchJson } from "@/lib/api-client";
import { apiErrorLabel } from "@/lib/error-label";

export function ProfilePanel() {
  const { t } = useI18n();
  const p = t.console.profile;
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [locale, setLocale] = useState("zh-CN");
  const { flash, setFlash } = useBootFlash(t.console.profile.loading);

  useEffect(() => {
    void (async () => {
      const result = await getJson("/api/auth/profile");
      if (!result.ok) {
        setFlash(errFlash(apiErrorLabel(t, result.envelope, t.console.profile.loadFail)));
        return;
      }
      const data = result.envelope.data;
      setName(typeof data?.display_name === "string" ? data.display_name : "");
      setTimezone(typeof data?.timezone === "string" ? data.timezone : "UTC");
      setLocale(typeof data?.locale === "string" ? data.locale : "zh-CN");
      setFlash(null);
    })();
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    const result = await patchJson("/api/auth/profile", { display_name: name, timezone, locale });
    setFlash(resultFlash(result.ok, t.console.profile.saved, apiErrorLabel(t, result.envelope, t.console.profile.saveFail)));
  }

  return (
    <section className="max-w-xl space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">{p.title}</h1>
      <p className="text-sm text-foreground/70">{p.lead}</p>
      {flash ? <FlashBanner flash={flash} compact className="mt-0" /> : null}
      <form className="space-y-3" onSubmit={save}>
        <input
          className="w-full rounded-md border border-border px-3 py-2 text-sm"
          placeholder={p.displayName}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <input
          className="w-full rounded-md border border-border px-3 py-2 text-sm"
          placeholder={p.timezonePlaceholder}
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
        />
        <select
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
          value={locale}
          onChange={(event) => setLocale(event.target.value)}
          aria-label={p.locale}
        >
          <option value="zh-CN">简体中文</option>
          <option value="zh-TW">繁體中文</option>
          <option value="en">English</option>
        </select>
        <Button type="submit">{p.save}</Button>
      </form>
    </section>
  );
}
