export const LOCALE_COOKIE = "locale";

export const LOCALES = ["en", "zh-CN", "zh-TW"] as const;

export type Locale = (typeof LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  "zh-CN": "简体中文",
  "zh-TW": "繁體中文",
};

export function parseLocale(value: string | undefined | null): Locale | null {
  if (value === "en" || value === "zh-CN" || value === "zh-TW") {
    return value;
  }
  return null;
}

const TRADITIONAL_REGIONS = new Set(["TW", "HK", "MO"]);

const MAINLAND_TIME_ZONES = new Set([
  "Asia/Shanghai",
  "Asia/Urumqi",
  "Asia/Chongqing",
  "Asia/Harbin",
  "Asia/Kashgar",
  "Asia/Chungking",
]);

const TRADITIONAL_TIME_ZONES = new Set(["Asia/Taipei", "Asia/Hong_Kong", "Asia/Macau"]);

export function localeFromCountry(code: string | undefined | null): Locale | null {
  const country = code?.trim().toUpperCase() ?? "";
  if (!/^[A-Z]{2}$/.test(country) || country === "XX") {
    return null;
  }
  if (country === "CN") {
    return "zh-CN";
  }
  if (TRADITIONAL_REGIONS.has(country)) {
    return "zh-TW";
  }
  return "en";
}

export function localeFromTimeZone(timeZone: string | undefined | null): Locale | null {
  const zone = timeZone?.trim() ?? "";
  if (MAINLAND_TIME_ZONES.has(zone)) {
    return "zh-CN";
  }
  if (TRADITIONAL_TIME_ZONES.has(zone)) {
    return "zh-TW";
  }
  if (!zone.includes("/") || zone === "Etc/UTC" || zone.startsWith("Etc/GMT")) {
    return null;
  }
  return "en";
}

export function localeFromLanguageTag(tag: string): Locale | null {
  const parts = tag.toLowerCase().split("-").filter(Boolean);
  const language = parts[0];
  if (!language) {
    return null;
  }
  const subtags = parts.slice(1);
  const region = subtags.find((part) => part.length === 2 || /^\d{3}$/.test(part));
  const script = subtags.find((part) => part.length === 4);
  if (region && TRADITIONAL_REGIONS.has(region.toUpperCase())) {
    return "zh-TW";
  }
  if (region === "cn") {
    return "zh-CN";
  }
  if (language === "zh") {
    if (script === "hant") {
      return "zh-TW";
    }
    if (script === "hans" || !region) {
      return "zh-CN";
    }
    return "en";
  }
  if (language === "en") {
    return "en";
  }
  return null;
}

export function localeFromAcceptLanguage(header: string): Locale {
  const ranked = header.split(",").flatMap((part, index) => {
    const [raw, ...params] = part.split(";");
    const tag = raw?.trim().toLowerCase() ?? "";
    if (!tag) {
      return [];
    }
    const qParam = params.find((item) => item.trim().toLowerCase().startsWith("q="));
    const q = qParam ? Number(qParam.trim().slice(2)) : 1;
    return [{ tag, q: Number.isFinite(q) ? q : 0, index }];
  });
  ranked.sort((left, right) => right.q - left.q || left.index - right.index);
  const primary = ranked[0]?.tag;
  if (!primary) {
    return "en";
  }
  return localeFromLanguageTag(primary) ?? "en";
}

export function localeFromSignals(input: { country?: string | null; acceptLanguage?: string | null }): Locale {
  return localeFromCountry(input.country) ?? localeFromAcceptLanguage(input.acceptLanguage ?? "");
}

export function localeFromClient(timeZone: string, acceptLanguage: string): Locale {
  return localeFromTimeZone(timeZone) ?? localeFromAcceptLanguage(acceptLanguage);
}

export function htmlLang(locale: Locale): string {
  return locale;
}

export function readLocaleCookie(): Locale | null {
  const prefix = `${LOCALE_COOKIE}=`;
  const found = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return parseLocale(found?.slice(prefix.length));
}

export function writeLocaleCookie(locale: Locale) {
  document.cookie = `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`;
}
