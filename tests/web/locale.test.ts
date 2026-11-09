import { describe, expect, it } from "vitest";

import { estimateUsage } from "../../apps/web/src/lib/estimate";
import {
  localeFromAcceptLanguage,
  localeFromClient,
  localeFromCountry,
  localeFromSignals,
  localeFromTimeZone,
  parseLocale,
} from "../../apps/web/src/lib/locale";

describe("界面语言", () => {
  it("识别英文、简体和繁体", () => {
    expect(parseLocale("en")).toBe("en");
    expect(parseLocale("zh-CN")).toBe("zh-CN");
    expect(parseLocale("zh-TW")).toBe("zh-TW");
    expect(parseLocale("zh")).toBeNull();
    expect(localeFromAcceptLanguage("zh-TW,zh;q=0.9,en;q=0.8")).toBe("zh-TW");
    expect(localeFromAcceptLanguage("zh-HK,en;q=0.5")).toBe("zh-TW");
    expect(localeFromAcceptLanguage("zh-MO")).toBe("zh-TW");
    expect(localeFromAcceptLanguage("zh-Hant")).toBe("zh-TW");
    expect(localeFromAcceptLanguage("zh-CN,zh;q=0.9")).toBe("zh-CN");
    expect(localeFromAcceptLanguage("zh-Hans")).toBe("zh-CN");
    expect(localeFromAcceptLanguage("en;q=0.4,zh-TW;q=0.9")).toBe("zh-TW");
    expect(localeFromAcceptLanguage("en-US,en;q=0.8")).toBe("en");
    expect(localeFromAcceptLanguage("en-TW")).toBe("zh-TW");
    expect(localeFromAcceptLanguage("en-CN")).toBe("zh-CN");
    expect(localeFromAcceptLanguage("zh-SG")).toBe("en");
    expect(localeFromAcceptLanguage("ja,zh-CN;q=0.9,en;q=0.8")).toBe("en");
    expect(localeFromAcceptLanguage("")).toBe("en");
  });

  it("按地区决定默认语言，地区优先于浏览器语言", () => {
    expect(localeFromCountry("CN")).toBe("zh-CN");
    expect(localeFromCountry("tw")).toBe("zh-TW");
    expect(localeFromCountry("HK")).toBe("zh-TW");
    expect(localeFromCountry("MO")).toBe("zh-TW");
    expect(localeFromCountry("US")).toBe("en");
    expect(localeFromCountry("JP")).toBe("en");
    expect(localeFromCountry("XX")).toBeNull();
    expect(localeFromCountry("")).toBeNull();
    expect(localeFromSignals({ country: "US", acceptLanguage: "zh-CN" })).toBe("en");
    expect(localeFromSignals({ country: "TW", acceptLanguage: "en-US" })).toBe("zh-TW");
    expect(localeFromSignals({ country: "CN", acceptLanguage: "en-US" })).toBe("zh-CN");
    expect(localeFromSignals({ country: null, acceptLanguage: "zh-HK" })).toBe("zh-TW");
    expect(localeFromSignals({ country: null, acceptLanguage: "fr-FR" })).toBe("en");
  });

  it("用时区代表所在地区", () => {
    expect(localeFromTimeZone("Asia/Shanghai")).toBe("zh-CN");
    expect(localeFromTimeZone("Asia/Urumqi")).toBe("zh-CN");
    expect(localeFromTimeZone("Asia/Taipei")).toBe("zh-TW");
    expect(localeFromTimeZone("Asia/Hong_Kong")).toBe("zh-TW");
    expect(localeFromTimeZone("Asia/Macau")).toBe("zh-TW");
    expect(localeFromTimeZone("America/New_York")).toBe("en");
    expect(localeFromTimeZone("Asia/Tokyo")).toBe("en");
    expect(localeFromTimeZone("UTC")).toBeNull();
    expect(localeFromClient("America/Los_Angeles", "zh-CN,zh;q=0.9")).toBe("en");
    expect(localeFromClient("Asia/Hong_Kong", "en-US,en;q=0.8")).toBe("zh-TW");
    expect(localeFromClient("Asia/Shanghai", "en-US")).toBe("zh-CN");
    expect(localeFromClient("UTC", "zh-TW")).toBe("zh-TW");
    expect(localeFromClient("UTC", "de-DE")).toBe("en");
  });

  it("按示意用量落到现有充值档", () => {
    expect(estimateUsage("chat", "light").suggestedUsd).toBe(10);
    expect(estimateUsage("coding", "regular").suggestedUsd).toBe(50);
    expect(estimateUsage("agents", "heavy").suggestedUsd).toBe(100);
  });
});
