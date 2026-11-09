import type { Messages } from "@/content/messages";

/** 种子/历史套餐名 → 当前语言展示名；自定义名原样返回。 */
export function productDisplayName(t: Messages, name: string): string {
  const map = t.admin.pages.products.seedNames as Record<string, string>;
  return map[name] || name;
}
