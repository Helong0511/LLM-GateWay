import { ConsoleNav } from "@/components/console-nav";
import { InvoicePanel } from "@/components/ops-panels";
import { SiteShell } from "@/components/site-shell";

export default function ConsoleInvoicesPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <InvoicePanel />
    </SiteShell>
  );
}
