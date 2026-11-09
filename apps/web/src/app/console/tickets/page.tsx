import { ConsoleNav } from "@/components/console-nav";
import { TicketPanel } from "@/components/ops-panels";
import { SiteShell } from "@/components/site-shell";

export default function ConsoleTicketsPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <TicketPanel />
    </SiteShell>
  );
}
