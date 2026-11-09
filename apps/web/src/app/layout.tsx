import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Space_Grotesk } from "next/font/google";

import { LocaleProvider } from "@/components/locale-provider";
import { messages } from "@/content";
import { htmlLang } from "@/lib/locale";
import { resolveLocale } from "@/lib/locale-server";

import "./globals.css";

const bodyFont = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
  display: "swap",
});

const displayFont = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-code",
  display: "swap",
});

export async function generateMetadata(): Promise<Metadata> {
  const locale = await resolveLocale();
  return {
    title: messages[locale].meta.title,
    description: messages[locale].meta.description,
  };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await resolveLocale();
  return (
    <html lang={htmlLang(locale)} className={`${bodyFont.variable} ${displayFont.variable} ${monoFont.variable}`}>
      <body className="min-h-screen antialiased">
        <LocaleProvider initialLocale={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
