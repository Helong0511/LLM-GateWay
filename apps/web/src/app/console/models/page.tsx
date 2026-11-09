import { ConsoleNav } from "@/components/console-nav";
import { ModelsPanel } from "@/components/models-panel";
import { SiteShell } from "@/components/site-shell";

export default function ConsoleModelsPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <ModelsPanel />
    </SiteShell>
  );
}
