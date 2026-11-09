import type { Messages } from "@/content/messages";

/** 历史中文 title / 新写入的稳定码 → 文案键。 */
const TITLE_ALIAS: Record<string, keyof Messages["console"]["notifications"]["kinds"]> = {
  key_revoked: "keyRevoked",
  密钥已吊销: "keyRevoked",
  balance_low: "balanceLow",
  余额偏低: "balanceLow",
  key_expiry_7d: "keyExpiry7d",
  密钥即将到期: "keyExpiry7d",
  key_expiry_1d: "keyExpiry1d",
  密钥将在一天内到期: "keyExpiry1d",
};

const REASON_ALIAS: Record<string, keyof Messages["console"]["notifications"]["balanceReason"]> = {
  alerts_disabled: "alertsDisabled",
  余额预警已关闭: "alertsDisabled",
  checked: "checked",
  已检查: "checked",
  above_threshold: "aboveThreshold",
  可用余额高于预警线: "aboveThreshold",
};

export function notificationTitle(t: Messages, title: string): string {
  const key = TITLE_ALIAS[title];
  return key ? t.console.notifications.kinds[key].title : title;
}

export function notificationBody(t: Messages, title: string, body: string): string {
  const key = TITLE_ALIAS[title];
  if (!key) {
    return body;
  }
  const tmpl = t.console.notifications.kinds[key].body;
  if (key === "keyRevoked") {
    return tmpl.replace("{name}", body);
  }
  if (key === "balanceLow") {
    const [amount, currency] = body.includes("|") ? body.split("|", 2) : ["", ""];
    // 兼容旧中文 body
    if (!body.includes("|") && /[\u4e00-\u9fff]/.test(body)) {
      return body;
    }
    return tmpl.replace("{amount}", amount).replace("{currency}", currency);
  }
  if (key === "keyExpiry7d" || key === "keyExpiry1d") {
    const [name, when] = body.includes("|") ? body.split("|", 2) : [body, ""];
    if (!body.includes("|") && /[\u4e00-\u9fff]/.test(body)) {
      return body;
    }
    return tmpl.replace("{name}", name).replace("{when}", when);
  }
  return body;
}

export function balanceReasonLabel(t: Messages, reason: string): string {
  const key = REASON_ALIAS[reason];
  return key ? t.console.notifications.balanceReason[key] : reason;
}

export function paymentWarningLabel(t: Messages, warning: string | null | undefined): string | null {
  if (!warning) {
    return null;
  }
  if (warning === "usdt_wrong_chain" || warning.includes("错链") || warning.includes("错币")) {
    return t.console.billing.warnings.usdtWrongChain;
  }
  return warning;
}

export function billingNoteLabel(t: Messages, note: string): string {
  if (note === "available_formula" || note.includes("可用余额")) {
    return t.console.billing.availableFormula;
  }
  return note;
}
