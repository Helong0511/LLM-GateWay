import { BillingPanel } from "@/components/billing-panel";
import { ConsoleNav } from "@/components/console-nav";
import { SiteShell } from "@/components/site-shell";

export default function BillingPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <BillingPanel />
    </SiteShell>
  );
}
