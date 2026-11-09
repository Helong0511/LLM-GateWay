"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useI18n } from "@/components/locale-provider";

type Point = { day: string; requests: number; tokens: number };

export function TrendChart({ points }: { points: Point[] }) {
  const { t } = useI18n();
  if (points.length === 0) {
    return <p className="text-sm text-foreground/70">{t.common.trendEmpty}</p>;
  }
  return (
    <div className="h-56 w-full rounded-xl border border-border bg-card/60 p-3 text-accent">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey="day" stroke="hsl(var(--foreground) / 0.45)" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} stroke="hsl(var(--foreground) / 0.45)" tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey="requests" name={t.common.trendRequests} stroke="currentColor" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-2 text-xs text-foreground/60">{t.common.trendNote}</p>
    </div>
  );
}
