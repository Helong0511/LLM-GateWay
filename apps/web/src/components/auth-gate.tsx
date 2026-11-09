"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { getMeCached, postJson } from "@/lib/api-client";

/** 控制台/后台：会话失效时清 Cookie 并回到登录页。 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    void (async () => {
      const result = await getMeCached();
      if (!result.ok) {
        await postJson("/api/auth/logout", {});
        router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
        return;
      }
      setReady(true);
    })();
  }, [router]);

  if (!ready) {
    return <p className="text-sm text-foreground/70">{t.console.gateLoading}</p>;
  }
  return <>{children}</>;
}
