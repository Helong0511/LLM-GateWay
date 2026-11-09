import { ConsoleNav } from "@/components/console-nav";
import { ProfilePanel } from "@/components/profile-panel";
import { SiteShell } from "@/components/site-shell";

export default function ProfilePage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <ProfilePanel />
    </SiteShell>
  );
}
