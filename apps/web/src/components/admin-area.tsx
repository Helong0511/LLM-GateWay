"use client";

import { AdminGate } from "@/components/admin-gate";
import { AdminShell } from "@/components/admin-shell";

export function AdminArea({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <AdminShell>{children}</AdminShell>
    </AdminGate>
  );
}
