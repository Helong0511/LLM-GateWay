import { Suspense } from "react";

import { VerifyForm } from "@/components/auth-forms";
import { LocaleLoading } from "@/components/locale-loading";
import { SiteShell } from "@/components/site-shell";

export default function VerifyEmailPage() {
  return (
    <SiteShell>
      <Suspense fallback={<LocaleLoading k="openingVerify" />}>
        <VerifyForm />
      </Suspense>
    </SiteShell>
  );
}
