import { ConsoleNav } from "@/components/console-nav";
import { SiteShell } from "@/components/site-shell";
import { UsagePanel } from "@/components/usage-panel";

export default function UsagePage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <UsagePanel />
    </SiteShell>
  );
}
