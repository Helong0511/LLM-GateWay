import { en } from "@/content/en";
import type { Messages } from "@/content/messages";
import { zhCN } from "@/content/zh-CN";
import { zhTW } from "@/content/zh-TW";
import type { Locale } from "@/lib/locale";

export const messages: Record<Locale, Messages> = {
  en,
  "zh-CN": zhCN,
  "zh-TW": zhTW,
};
