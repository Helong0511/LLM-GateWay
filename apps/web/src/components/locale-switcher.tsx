"use client";

import { useI18n } from "@/components/locale-provider";
import { LOCALE_LABELS, LOCALES, type Locale } from "@/lib/locale";

const SHORT_LOCALE: Record<Locale, string> = {
  en: "EN",
  "zh-CN": "简",
  "zh-TW": "繁",
};

export function LocaleSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      className={`flex rounded-md border border-border bg-card/70 p-0.5 ${className}`.trim()}
      role="group"
      aria-label={t.shell.language}
    >
      {LOCALES.map((item) => (
        <button
          key={item}
          type="button"
          title={LOCALE_LABELS[item]}
          aria-label={LOCALE_LABELS[item]}
          className={
            item === locale
              ? "rounded px-2 py-1 font-mono text-xs font-medium text-accent"
              : "rounded px-2 py-1 font-mono text-xs text-foreground/55"
          }
          aria-pressed={item === locale}
          onClick={() => setLocale(item)}
        >
          {SHORT_LOCALE[item]}
        </button>
      ))}
    </div>
  );
}
