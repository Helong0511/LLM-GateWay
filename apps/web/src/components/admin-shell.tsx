"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { useI18n } from "@/components/locale-provider";
import { postJson } from "@/lib/api-client";

const NAV = [
  ["/admin", "overview"],
  ["/admin/users", "users"],
  ["/admin/providers", "providers"],
  ["/admin/models", "models"],
  ["/admin/deployments", "deployments"],
  ["/admin/keys", "keys"],
  ["/admin/orders", "orders"],
  ["/admin/products", "products"],
  ["/admin/refunds", "refunds"],
  ["/admin/ledger", "ledger"],
  ["/admin/usage", "usage"],
  ["/admin/crypto", "crypto"],
  ["/admin/health", "health"],
  ["/admin/audit", "audit"],
  ["/admin/routes", "routes"],
  ["/admin/settings", "settings"],
  ["/admin/backups", "backups"],
  ["/admin/announcements", "announcements"],
  ["/admin/tickets", "tickets"],
  ["/admin/invoices", "invoices"],
  ["/admin/coupons", "coupons"],
  ["/admin/margin", "margin"],
  ["/admin/content", "content"],
  ["/admin/tasks", "tasks"],
] as const;

export function AdminShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { t } = useI18n();
  const nav = t.admin.nav;
  const shell = t.admin.shell;

  async function logout() {
    await postJson("/api/auth/logout", {});
    router.push("/");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="flex items-center justify-between border-b border-border/80 bg-background/75 px-6 py-4 backdrop-blur-xl">
        <Link href="/admin" className="inline-flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="font-mono text-[10px] tracking-[0.16em] text-accent">OPS</span>
          {shell.brand}
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <LocaleSwitcher />
          <Link href="/console" className="rounded-md border border-accent/30 bg-accent/10 px-2.5 py-1 text-accent">
            {shell.toConsole}
          </Link>
          <Link href="/" className="text-foreground/70 hover:text-accent">
            {shell.toSite}
          </Link>
          <button type="button" className="text-foreground/70 hover:text-accent" onClick={() => void logout()}>
            {shell.logout}
          </button>
        </div>
      </header>
      <div className="grid gap-8 px-6 py-8 lg:grid-cols-[220px_1fr]">
        <nav className="space-y-1 text-sm">
          {NAV.map(([href, key]) => (
            <Link
              key={href}
              href={href}
              className="block rounded-md border border-transparent px-2.5 py-1.5 font-medium text-foreground/80 hover:border-accent/30 hover:bg-accent/5 hover:text-accent"
            >
              {nav[key]}
            </Link>
          ))}
        </nav>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
