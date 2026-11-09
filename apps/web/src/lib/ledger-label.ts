import type { Messages } from "@/content/messages";

/** 历史库内中文 reason → 稳定键；新写入也可直接用英文键。 */
const REASON_ALIAS: Record<string, keyof Messages["labels"]["ledgerReason"]> = {
  充值入账: "topup",
  充值赠送: "topupBonus",
  优惠券赠送: "couponBonus",
  退款: "refund",
  调用预扣: "hold",
  释放预扣: "releaseHold",
  无预扣的补扣: "catchUpNoHold",
  预扣转实扣: "settleHold",
  退回未使用的预扣: "refundUnusedHold",
  用量超出预扣的补扣: "catchUpOverHold",
  topup: "topup",
  topup_credit: "topup",
  topupBonus: "topupBonus",
  topup_bonus: "topupBonus",
  couponBonus: "couponBonus",
  coupon_bonus: "couponBonus",
  refund: "refund",
  hold: "hold",
  releaseHold: "releaseHold",
  release_hold: "releaseHold",
  catchUpNoHold: "catchUpNoHold",
  settleHold: "settleHold",
  refundUnusedHold: "refundUnusedHold",
  catchUpOverHold: "catchUpOverHold",
};

const TYPE_ALIAS: Record<string, keyof Messages["labels"]["ledgerType"]> = {
  bonus: "bonus",
  recharge: "recharge",
  adjust: "adjust",
  hold: "hold",
  hold_release: "release",
  release: "release",
  hold_commit: "settle",
  settle: "settle",
  consume: "usage",
  refund: "refund",
  usage: "usage",
};

export function ledgerReasonLabel(t: Messages, reason: string | null | undefined): string {
  if (!reason) {
    return t.admin.actions.none;
  }
  const key = REASON_ALIAS[reason] ?? REASON_ALIAS[reason.trim()];
  if (key) {
    return t.labels.ledgerReason[key];
  }
  return reason;
}

export function ledgerTypeLabel(t: Messages, entryType: string | null | undefined): string {
  if (!entryType) {
    return t.labels.common.unknown;
  }
  const key = TYPE_ALIAS[entryType] ?? TYPE_ALIAS[entryType.toLowerCase()];
  if (key) {
    return t.labels.ledgerType[key];
  }
  return entryType;
}

export function ledgerDirectionLabel(t: Messages, direction: string | null | undefined): string {
  if (direction === "C") {
    return t.labels.ledgerDirection.credit;
  }
  if (direction === "D") {
    return t.labels.ledgerDirection.debit;
  }
  return direction || t.labels.common.unknown;
}
