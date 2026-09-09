import React from "react";
import { CircleDot, FileText, MessageSquare, Upload, UserCog, Workflow } from "lucide-react";

import { formatDateTimeWIB, fromNow } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import { TIMELINE } from "@/constants/testIds";

/**
 * TimelineFeed — riwayat lintas-modul dalam SATU urutan waktu.
 *
 * Aturan keras (CR-10 pada audit V2): **setiap** baris menampilkan AKTOR-nya. Riwayat yang
 * tidak menyebut siapa yang mengerjakan tidak bisa dipakai untuk menyelesaikan perselisihan
 * (“siapa yang mengubah tahap ini?”) — itu sebabnya aktor bukan opsional di sini.
 *
 * items: [{ at, actor, kind, title, body, evidence: [{label, href}] }]
 */
const ICON = {
  stage: Workflow, activity: CircleDot, message: MessageSquare, document: FileText,
  upload: Upload, task: UserCog,
};

export default function TimelineFeed({ items = [], emptyText = "Belum ada riwayat.", testId }) {
  const rows = [...(items || [])]
    .filter((x) => x && x.at)
    .sort((a, b) => String(b.at).localeCompare(String(a.at)));

  if (!rows.length) {
    return (
      <p data-testid={TIMELINE.empty} className="rounded-lg border bg-card p-4 text-sm text-muted-foreground shadow-[var(--shadow-card)]">
        {emptyText}
      </p>
    );
  }

  return (
    <ol data-testid={testId || TIMELINE.feed} className="space-y-2">
      {rows.map((it, i) => {
        const Icon = ICON[it.kind] || CircleDot;
        return (
          <li key={`${it.at}-${i}`} data-testid={TIMELINE.item} data-kind={it.kind || "activity"}
            className="flex gap-3 rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
            <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center",
              "rounded-full bg-secondary text-muted-foreground")}>
              <Icon className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <p className="text-sm font-medium">{it.title}</p>
                <span className="text-xs text-muted-foreground" title={formatDateTimeWIB(it.at)}>
                  {fromNow(it.at)}
                </span>
              </div>
              {it.body ? <p className="mt-0.5 text-sm text-muted-foreground">{it.body}</p> : null}
              <p className="mt-1 text-xs text-muted-foreground">
                oleh <span data-testid={TIMELINE.actor} className="font-medium text-foreground">
                  {it.actor || "sistem"}
                </span>
                {" · "}{formatDateTimeWIB(it.at)}
              </p>
              {(it.evidence || []).length ? (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {it.evidence.map((e, j) => (
                    <a key={j} href={e.href} target="_blank" rel="noreferrer"
                      className="rounded border bg-secondary px-1.5 py-0.5 text-xs underline">
                      {e.label}
                    </a>
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
