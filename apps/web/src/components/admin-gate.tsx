"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { getMeCached, postJson } from "@/lib/api-client";
import { isStaffRoles } from "@/lib/guard";

export function AdminGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { t } = useI18n();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    void (async () => {
      const result = await getMeCached();
      if (!result.ok) {
        await postJson("/api/auth/logout", {});
        router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
        return;
      }
      if (!isStaffRoles(result.envelope.data?.roles)) {
        router.replace("/console");
        return;
      }
      setReady(true);
    })();
  }, [router]);

  if (!ready) {
    return <p className="text-sm text-foreground/70">{t.admin.shell.checking}</p>;
  }
  return <>{children}</>;
}
