import { ConsoleNav } from "@/components/console-nav";
import { NotificationsPanel } from "@/components/notifications-panel";
import { SiteShell } from "@/components/site-shell";

export default function NotificationsPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <NotificationsPanel />
    </SiteShell>
  );
}
