"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { useI18n } from "@/components/locale-provider";

/** 触发 RSC 重新执行服务端拉取，更新 /admin 首页快照指标。 */
export function OverviewRefresh() {
  const { t } = useI18n();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button
      type="button"
      className="rounded border border-border px-3 py-1 text-sm disabled:opacity-50"
      disabled={pending}
      title={t.admin.actions.refresh}
      onClick={() => startTransition(() => router.refresh())}
    >
      {t.admin.actions.refresh}
    </button>
  );
}
