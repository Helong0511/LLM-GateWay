"use client";

import { Suspense } from "react";

import { LoginForm } from "@/components/auth-forms";
import { useI18n } from "@/components/locale-provider";
import { SiteShell } from "@/components/site-shell";

export default function LoginPage() {
  const { t } = useI18n();
  return (
    <SiteShell>
      <Suspense fallback={<p className="text-sm">{t.auth.openingLogin}</p>}>
        <LoginForm />
      </Suspense>
    </SiteShell>
  );
}
