"use client";

import { notFound, useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/locale-provider";
import { DemoMark, SiteShell } from "@/components/site-shell";
import { getJson } from "@/lib/api-client";

type Notice = { title: string; body: string } | null;

export default function AnnouncementPage() {
  const params = useParams<{ slug: string }>();
  const { t } = useI18n();
  const [notice, setNotice] = useState<Notice>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    void (async () => {
      const result = await getJson(`/api/announcements/${params.slug}`);
      const data = result.envelope.data;
      if (result.ok && data && typeof data.title === "string" && typeof data.body === "string") {
        setNotice({ title: data.title, body: data.body });
        setMissing(false);
        return;
      }
      setNotice(null);
      setMissing(true);
    })();
  }, [params.slug]);

  if (missing && params.slug !== "welcome") {
    notFound();
  }
  const title = notice?.title ?? (params.slug === "welcome" ? t.announcement.title : "");
  const body = notice?.body ?? (params.slug === "welcome" ? t.announcement.body : "");
  if (!title && !missing) {
    return (
      <SiteShell>
        <p className="text-sm">{t.common.loadingAnnouncement}</p>
      </SiteShell>
    );
  }
  return (
    <SiteShell>
      <article className="max-w-3xl">
        {notice ? null : <DemoMark />}
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-4 text-sm leading-6 text-foreground/80">{body}</p>
      </article>
    </SiteShell>
  );
}
