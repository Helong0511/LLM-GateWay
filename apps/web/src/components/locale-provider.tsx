"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useSyncExternalStore } from "react";

import { messages } from "@/content";
import type { Messages } from "@/content/messages";
import { htmlLang, localeFromClient, readLocaleCookie, writeLocaleCookie, type Locale } from "@/lib/locale";

type LocaleValue = {
  locale: Locale;
  t: Messages;
  setLocale: (locale: Locale) => void;
};

const LocaleContext = createContext<LocaleValue | null>(null);
const listeners = new Set<() => void>();
let selectedLocale: Locale | null = null;

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emitLocale() {
  for (const listener of listeners) {
    listener();
  }
}

function clientLocale(): Locale {
  if (selectedLocale) {
    return selectedLocale;
  }
  const stored = readLocaleCookie();
  if (stored) {
    return stored;
  }
  const languages = navigator.languages.length > 0 ? navigator.languages : [navigator.language];
  return localeFromClient(Intl.DateTimeFormat().resolvedOptions().timeZone, languages.join(","));
}

export function LocaleProvider({ initialLocale, children }: { initialLocale: Locale; children: React.ReactNode }) {
  const router = useRouter();
  const getServerLocale = useCallback(() => initialLocale, [initialLocale]);
  const locale = useSyncExternalStore(subscribe, clientLocale, getServerLocale);

  useEffect(() => {
    const stored = readLocaleCookie();
    if (stored) {
      document.documentElement.lang = htmlLang(stored);
      return;
    }
    const languages = navigator.languages.length > 0 ? navigator.languages : [navigator.language];
    const detected = localeFromClient(Intl.DateTimeFormat().resolvedOptions().timeZone, languages.join(","));
    selectedLocale = detected;
    writeLocaleCookie(detected);
    document.documentElement.lang = htmlLang(detected);
    emitLocale();
    if (detected !== initialLocale) {
      router.refresh();
    }
  }, [initialLocale, router]);

  function setLocale(next: Locale) {
    selectedLocale = next;
    writeLocaleCookie(next);
    document.documentElement.lang = htmlLang(next);
    emitLocale();
    router.refresh();
  }

  return (
    <LocaleContext.Provider value={{ locale, t: messages[locale], setLocale }}>{children}</LocaleContext.Provider>
  );
}

export function useI18n(): LocaleValue {
  const value = useContext(LocaleContext);
  if (!value) {
    throw new Error("useI18n must be used within LocaleProvider");
  }
  return value;
}
