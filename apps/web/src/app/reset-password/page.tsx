import { Suspense } from "react";

import { ResetForm } from "@/components/auth-forms";
import { LocaleLoading } from "@/components/locale-loading";
import { SiteShell } from "@/components/site-shell";

export default function ResetPasswordPage() {
  return (
    <SiteShell>
      <Suspense fallback={<LocaleLoading k="openingReset" />}>
        <ResetForm />
      </Suspense>
    </SiteShell>
  );
}
