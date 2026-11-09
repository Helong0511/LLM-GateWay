"use client";

import { useI18n } from "@/components/locale-provider";

type LoadingKey = "loadingAnnouncement" | "openingReset" | "openingVerify";

export function LocaleLoading({ k }: { k: LoadingKey }) {
  const { t } = useI18n();
  return <p className="text-sm">{t.common[k]}</p>;
}
