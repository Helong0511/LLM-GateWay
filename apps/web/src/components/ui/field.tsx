import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** 表单项：标题 + 可选说明 + 控件，避免只有 placeholder、看不懂第几项是什么。 */
export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("grid gap-1 text-sm", className)}>
      <span className="font-medium text-foreground">{label}</span>
      {hint ? <span className="text-xs leading-5 text-foreground/60">{hint}</span> : null}
      {children}
    </label>
  );
}
