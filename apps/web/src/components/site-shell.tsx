"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { LocaleSwitcher } from "@/components/locale-switcher";
import { useI18n } from "@/components/locale-provider";
import { Button } from "@/components/ui/button";
import { getMeCached, postJson } from "@/lib/api-client";
import { isStaffRoles } from "@/lib/guard";

const themeListeners = new Set<() => void>();

function subscribeTheme(listener: () => void) {
  themeListeners.add(listener);
  return () => themeListeners.delete(listener);
}

function readTheme() {
  const stored = window.localStorage.getItem("theme");
  if (stored === "dark" || stored === "light") {
    return stored === "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function SiteShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useI18n();
  const dark = useSyncExternalStore(subscribeTheme, readTheme, () => false);
  const [signedIn, setSignedIn] = useState(false);
  const [isStaff, setIsStaff] = useState(false);
  const [email, setEmail] = useState("");
  const nav = [
    ["/", t.shell.nav.home],
    ["/models", t.shell.nav.models],
    ["/pricing", t.shell.nav.pricing],
    ["/docs", t.shell.nav.docs],
    ["/status", t.shell.nav.status],
  ] as const;
  const accountLinks = (
    signedIn
      ? [
        ["/console", t.shell.nav.console],
        ...(isStaff ? [["/admin", t.shell.admin] as const] : []),
        ["/console/security", t.shell.security],
        ["/contact", t.shell.footer.contact],
        ["/terms", t.shell.footer.terms],
        ["/privacy", t.shell.footer.privacy],
      ]
      : [
        ["/login", t.shell.nav.login],
        ["/register", t.shell.nav.register],
        ["/console", t.shell.nav.console],
        ["/contact", t.shell.footer.contact],
        ["/terms", t.shell.footer.terms],
        ["/privacy", t.shell.footer.privacy],
      ]
  ) as ReadonlyArray<readonly [string, string]>;
  const columns = [
    {
      title: t.shell.groups.product,
      links: [
        ["/features", t.shell.footer.features],
        ["/solutions", t.shell.footer.solutions],
        ["/models", t.shell.nav.models],
        ["/pricing", t.shell.nav.pricing],
      ],
    },
    {
      title: t.shell.groups.developers,
      links: [
        ["/docs", t.shell.nav.docs],
        ["/quickstart", t.shell.footer.quickstart],
        ["/status", t.shell.nav.status],
        ["/faq", t.shell.footer.faq],
      ],
    },
    {
      title: t.shell.groups.account,
      links: accountLinks,
    },
  ] as const;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    void (async () => {
      const result = await getMeCached();
      if (!result.ok || !result.envelope.data?.user || typeof result.envelope.data.user !== "object") {
        setSignedIn(false);
        setIsStaff(false);
        setEmail("");
        return;
      }
      const user = result.envelope.data.user as Record<string, unknown>;
      setSignedIn(true);
      setIsStaff(isStaffRoles(result.envelope.data.roles));
      setEmail(typeof user.email === "string" ? user.email : "");
    })();
  }, [pathname]);

  function toggleTheme() {
    window.localStorage.setItem("theme", dark ? "light" : "dark");
    for (const listener of themeListeners) {
      listener();
    }
  }

  async function logout() {
    await postJson("/api/auth/logout", {});
    setSignedIn(false);
    setIsStaff(false);
    setEmail("");
    router.push("/");
    router.refresh();
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border/80 bg-background/75 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-6 py-3">
          <Link href="/" className="mr-2 inline-flex items-center gap-2 text-sm font-semibold tracking-tight">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-[4px] border border-accent/50 bg-accent/10 font-mono text-[10px] text-accent">
              F
            </span>
            <span>{t.shell.brand}</span>
          </Link>
          <nav className="flex flex-1 flex-wrap gap-1 text-sm">
            {nav.map(([href, label]) => {
              const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  className={
                    active
                      ? "rounded-md border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-accent"
                      : "rounded-md px-2.5 py-1.5 text-foreground/70 hover:bg-muted hover:text-foreground"
                  }
                >
                  {label}
                </Link>
              );
            })}
          </nav>
          <div className="flex flex-wrap items-center gap-2">
            <LocaleSwitcher />
            <Button variant="outline" size="sm" onClick={toggleTheme} aria-pressed={dark}>
              {dark ? t.shell.useLight : t.shell.useDark}
            </Button>
            {signedIn ? (
              <>
                <Link href="/console" className="max-w-[10rem] truncate px-2 text-sm text-foreground/80" title={email}>
                  {email || t.shell.nav.console}
                </Link>
                {isStaff ? (
                  <Link href="/admin" className="px-2 text-sm text-accent">
                    {t.shell.admin}
                  </Link>
                ) : null}
                <Link
                  href="/console"
                  className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-[0_0_0_1px_hsl(var(--accent)/0.25)]"
                >
                  {t.shell.nav.console}
                </Link>
                <Button variant="outline" size="sm" onClick={() => void logout()}>
                  {t.shell.logout}
                </Button>
              </>
            ) : (
              <>
                <Link href="/login" className="px-2 text-sm text-foreground/80">
                  {t.shell.nav.login}
                </Link>
                <Link
                  href="/register"
                  className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-[0_0_0_1px_hsl(var(--accent)/0.25)]"
                >
                  {t.shell.nav.register}
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto flex max-w-6xl flex-col gap-14 px-6 py-12">{children}</main>
      <footer className="border-t border-border/80 bg-card/40">
        <div className="mx-auto grid max-w-6xl gap-8 px-6 py-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-sm font-semibold">{t.shell.brand}</p>
            <p className="mt-2 text-sm leading-6 text-foreground/65">{t.meta.description}</p>
          </div>
          {columns.map((column) => (
            <div key={column.title}>
              <p className="text-xs font-medium tracking-wide text-foreground/50">{column.title}</p>
              <ul className="mt-3 space-y-2 text-sm">
                {column.links.map(([href, label]) => (
                  <li key={href}>
                    <Link href={href} className="text-foreground/75 hover:text-foreground">
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </footer>
    </div>
  );
}

export function DemoMark() {
  const { t } = useI18n();
  return <span className="rounded border border-dashed border-border px-1.5 py-0.5 text-xs">{t.shell.demo}</span>;
}
