import { cookies, headers } from "next/headers";

import { LOCALE_COOKIE, localeFromSignals, parseLocale, type Locale } from "@/lib/locale";

const COUNTRY_HEADERS = [
  "cf-ipcountry",
  "cloudfront-viewer-country",
  "x-vercel-ip-country",
  "x-country-code",
  "x-appengine-country",
] as const;

export async function resolveLocale(): Promise<Locale> {
  const jar = await cookies();
  const stored = parseLocale(jar.get(LOCALE_COOKIE)?.value);
  if (stored) {
    return stored;
  }
  const headerList = await headers();
  const country = COUNTRY_HEADERS.map((name) => headerList.get(name)).find((value) => value?.trim());
  return localeFromSignals({ country, acceptLanguage: headerList.get("accept-language") });
}
