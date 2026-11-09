"use client";

import { useI18n } from "@/components/locale-provider";
import { Button } from "@/components/ui/button";

/**
 * 手动重新拉取当前面板数据的按钮：
 * 数据被后台任务、支付回调或他人变更时，无需刷新浏览器即可看到最新列表。
 */
export function RefreshButton({
  onRefresh,
  disabled,
}: {
  onRefresh: () => void | Promise<void>;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={disabled}
      onClick={() => void onRefresh()}
      title={t.admin.actions.refresh}
    >
      {t.admin.actions.refresh}
    </Button>
  );
}
