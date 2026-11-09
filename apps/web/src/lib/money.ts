/** 客户侧展示金额：去掉多余尾零，最多保留 4 位小数。账本仍按后端精度。 */
export function displayMoney(value: string | null | undefined, currency = "USD"): string {
  if (value == null || value === "") {
    return "—";
  }
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`.trim();
  }
  const fixed = amount.toFixed(4).replace(/\.?0+$/, "");
  return currency ? `${fixed} ${currency}` : fixed;
}
