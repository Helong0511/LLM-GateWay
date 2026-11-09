"use client";

import { useI18n } from "@/components/locale-provider";
import { Button } from "@/components/ui/button";

export function PageControls({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const { t } = useI18n();
  const pages = Math.max(1, Math.ceil(Math.max(total, 0) / Math.max(pageSize, 1)));
  const summary = t.common.pageOf
    .replace("{page}", String(page))
    .replace("{pages}", String(pages))
    .replace("{total}", String(total));
  return (
    <div className="flex items-center gap-3 text-sm">
      <Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        {t.common.prevPage}
      </Button>
      <span>{summary}</span>
      <Button type="button" variant="outline" size="sm" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
        {t.common.nextPage}
      </Button>
    </div>
  );
}
