import type { Messages } from "@/content/messages";

type LabelGroup = keyof Messages["labels"];

/** 按当前页面语言显示状态/渠道等枚举文案；未知码回退原文。 */
export function statusLabel(t: Messages, group: LabelGroup, code: string | null | undefined): string {
  if (!code) {
    return t.labels.common.unknown;
  }
  const map = t.labels[group] as Record<string, string>;
  return map[code] ?? code;
}
