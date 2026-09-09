import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlarmClock, ArrowUpRight, AtSign, Banknote, Bell, CheckCheck, ChevronDown, ChevronRight,
  HardHat, Info, LifeBuoy, Users, X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import { fromNow } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import { NOTIF } from "@/constants/testIds";

export const CATEGORY_ICON = {
  tugas: AlarmClock, keuangan: Banknote, penjualan: Users, proyek: HardHat,
  layanan: LifeBuoy, sebutan: AtSign, sistem: Info,
};

// Warna per kategori (kelas LITERAL — jangan dirakit dinamis, pelajaran regresi pill:
// Tailwind hanya mengompilasi kelas yang tertulis di sumber).
export const CATEGORY_TONE = {
  tugas: "bg-amber-100 text-amber-700",
  keuangan: "bg-emerald-100 text-emerald-700",
  penjualan: "bg-sky-100 text-sky-700",
  proyek: "bg-orange-100 text-orange-700",
  layanan: "bg-violet-100 text-violet-700",
  sebutan: "bg-pink-100 text-pink-700",
  sistem: "bg-slate-200 text-slate-600",
};

/**
 * NotificationRows — daftar notifikasi RINGKAS (Fase 64).
 *
 * Bentuk lamanya: satu kartu tinggi per notifikasi (judul + isi + waktu, tiga baris) tanpa
 * kategori dan tanpa tautan, sehingga 40 notifikasi = layar sepanjang lima kali lipat yang
 * tidak menolong siapa pun. Di sini satu notifikasi = SATU baris padat: ikon kategori,
 * judul, isi terpangkas satu baris, waktu, dan tombol yang benar-benar membawa pemakai ke
 * pekerjaannya. Notifikasi yang tindakannya sudah dilakukan tampil dengan keterangan
 * "sudah ditangani" — bukan tetap berdiri seperti tugas yang belum selesai.
 */
export default function NotificationRows({ rows = [], onRead, onDismiss, emptyState,
  onGroupRead, onGroupDismiss }) {
  const navigate = useNavigate();
  const [terbuka, setTerbuka] = useState({});

  if (!rows.length) {
    return (
      <EmptyState testId={NOTIF.empty} icon={Bell} title={emptyState?.title || "Bersih"}
        description={emptyState?.description
          || "Tidak ada notifikasi pada tampilan ini."}
        actionLabel={emptyState?.actionLabel} onAction={emptyState?.onAction} />
    );
  }

  const open = async (n) => {
    if (!n.read) await onRead(n, { silent: true });
    if (n.link) navigate(n.link);
  };

  return (
    <ul className="divide-y rounded-xl border bg-card shadow-[var(--shadow-card)]">
      {rows.map((n) => {
        const Icon = CATEGORY_ICON[n.category] || Info;
        const kembar = (n.group_count || 1) > 1;
        const buka = !!terbuka[n.group_key];
        return (
          <li key={n.group_key || n.id} data-testid={NOTIF.item} data-category={n.category}
            data-read={n.read ? "1" : "0"} data-group-count={n.group_count || 1}
            className={cn("group px-3 py-2 transition-colors hover:bg-secondary/60",
              !n.read && "bg-accent/30")}>
            <div className="flex items-center gap-3">
            {kembar ? (
              <button type="button" data-testid={`${NOTIF.groupExpand}-${n.category}`}
                aria-label={buka ? "Tutup kelompok" : `Lihat ${n.group_count} notifikasi kembar`}
                onClick={() => setTerbuka((t) => ({ ...t, [n.group_key]: !t[n.group_key] }))}
                className="flex h-7 w-5 shrink-0 items-center justify-center text-muted-foreground">
                {buka ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
            ) : null}
            <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
              CATEGORY_TONE[n.category] || CATEGORY_TONE.sistem,
              n.read && "opacity-50")}>
              <Icon className="h-3.5 w-3.5" />
            </span>

            <button type="button" onClick={() => open(n)}
              className="min-w-0 flex-1 text-left">
              <span className="flex items-center gap-1.5">
                {!n.read ? <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" /> : null}
                {kembar ? (
                  <span data-testid={NOTIF.groupCount}
                    className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-primary">
                    {n.group_count}×
                  </span>
                ) : null}
                <span className={cn("truncate text-sm", !n.read && "font-semibold")}>
                  {n.title}
                </span>
                {n.needs_action && !n.resolved_at ? (
                  <span data-testid={NOTIF.actionBadge}
                    className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-amber-900">
                    perlu tindakan
                  </span>
                ) : null}
                {n.resolved_at ? (
                  <span data-testid={NOTIF.resolvedNote}
                    className="shrink-0 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800">
                    sudah ditangani
                  </span>
                ) : null}
              </span>
              <span className="flex items-baseline gap-2">
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  {kembar
                    ? `${n.group_unread} belum dibaca · terlama ${fromNow(n.group_oldest_at)}`
                    : (n.body || "—")}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                  {fromNow(n.created_at)}
                </span>
              </span>
            </button>

            <div className="flex shrink-0 items-center gap-0.5">
              {n.link ? (
                <Button size="icon" variant="ghost" data-testid={NOTIF.openBtn}
                  aria-label={`Buka ${n.title}`} onClick={() => open(n)}
                  className="h-7 w-7 opacity-60 group-hover:opacity-100">
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Button>
              ) : null}
              {kembar ? (
                <>
                  <Button size="icon" variant="ghost" data-testid={NOTIF.groupReadBtn}
                    aria-label={`Tandai ${n.group_count} notifikasi ini dibaca`}
                    onClick={() => onGroupRead?.(n)}
                    className="h-7 w-7 opacity-60 group-hover:opacity-100">
                    <CheckCheck className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" data-testid={NOTIF.groupDismissBtn}
                    aria-label={`Sembunyikan ${n.group_count} notifikasi ini`}
                    onClick={() => onGroupDismiss?.(n)}
                    className="h-7 w-7 opacity-60 group-hover:opacity-100">
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </>
              ) : (
                <>
                  {!n.read ? (
                    <Button size="icon" variant="ghost" aria-label={`Tandai dibaca ${n.title}`}
                      onClick={() => onRead(n)}
                      className="h-7 w-7 opacity-60 group-hover:opacity-100">
                      <CheckCheck className="h-3.5 w-3.5" />
                    </Button>
                  ) : null}
                  <Button size="icon" variant="ghost" data-testid={NOTIF.dismissBtn}
                    aria-label={`Sembunyikan ${n.title}`} onClick={() => onDismiss(n)}
                    className="h-7 w-7 opacity-60 group-hover:opacity-100">
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </>
              )}
            </div>
            </div>

            {kembar && buka ? (
              <ul className="mt-1 space-y-0.5 border-l pl-6">
                {(n.group_members || []).map((m) => (
                  <li key={m.id} data-testid={NOTIF.groupMember}
                    className="flex items-baseline gap-2 py-0.5 text-xs">
                    <button type="button" onClick={() => open({ ...m, category: n.category })}
                      className="min-w-0 flex-1 truncate text-left hover:underline">
                      {m.title}{m.body ? ` — ${m.body}` : ""}
                    </button>
                    <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                      {fromNow(m.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
