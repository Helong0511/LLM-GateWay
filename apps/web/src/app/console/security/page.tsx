import { ConsoleNav } from "@/components/console-nav";
import { SecurityPanel } from "@/components/security-panel";
import { SiteShell } from "@/components/site-shell";

export default function SecurityPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <SecurityPanel />
    </SiteShell>
  );
}
