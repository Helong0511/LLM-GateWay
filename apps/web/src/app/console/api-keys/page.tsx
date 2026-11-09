import { ConsoleNav } from "@/components/console-nav";
import { KeysPanel } from "@/components/keys-panel";
import { SiteShell } from "@/components/site-shell";

export default function ApiKeysPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <KeysPanel />
    </SiteShell>
  );
}
