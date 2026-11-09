import { ConsoleNav } from "@/components/console-nav";
import { CouponRedeem } from "@/components/ops-panels";
import { SiteShell } from "@/components/site-shell";

export default function ConsoleCouponsPage() {
  return (
    <SiteShell>
      <ConsoleNav />
      <CouponRedeem />
    </SiteShell>
  );
}
