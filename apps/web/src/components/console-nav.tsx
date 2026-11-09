"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { getMeCached } from "@/lib/api-client";
import { isStaffRoles } from "@/lib/guard";

const PRIMARY = [
  ["/console", "dashboard"],
  ["/console/models", "models"],
  ["/console/api-keys", "apiKeys"],
  ["/console/usage", "usage"],
  ["/console/billing", "billing"],
] as const;

const SECONDARY = [
  ["/console/coupons", "coupons"],
  ["/console/tickets", "tickets"],
  ["/console/invoices", "invoices"],
  ["/console/notifications", "notifications"],
  ["/console/profile", "profile"],
  ["/console/security", "security"],
] as const;

function NavLink({ href, label, pathname }: { href: string; label: string; pathname: string }) {
  const active = href === "/console" ? pathname === "/console" : pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      className={
        active
          ? "rounded-md border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-accent"
          : "rounded-md border border-border/80 bg-card/70 px-2.5 py-1.5 text-foreground/75 transition-colors hover:border-accent/40 hover:text-accent"
      }
    >
      {label}
    </Link>
  );
}

export function ConsoleNav() {
  const pathname = usePathname() || "/console";
  const { t } = useI18n();
  const nav = t.shell.consoleNav;
  const [isStaff, setIsStaff] = useState(false);

  useEffect(() => {
    void (async () => {
      const result = await getMeCached();
      setIsStaff(result.ok && isStaffRoles(result.envelope.data?.roles));
    })();
  }, []);

  return (
    <div className="space-y-2">
      {isStaff ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Link href="/admin" className="rounded-md border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-accent">
            {t.shell.toAdmin}
          </Link>
          <span className="text-foreground/55">{t.shell.consoleView}</span>
        </div>
      ) : null}
      <nav className="flex flex-wrap gap-2 text-sm" aria-label={t.shell.nav.console}>
        {PRIMARY.map(([href, key]) => (
          <NavLink key={href} href={href} label={nav[key]} pathname={pathname} />
        ))}
      </nav>
      <nav className="flex flex-wrap gap-2 text-sm" aria-label={t.shell.nav.console}>
        {SECONDARY.map(([href, key]) => (
          <NavLink key={href} href={href} label={nav[key]} pathname={pathname} />
        ))}
      </nav>
    </div>
  );
}
