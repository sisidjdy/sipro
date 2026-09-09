import React, { useState } from "react";
import { ChevronDown, ChevronUp, CloudOff, RefreshCw, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import OfflineQueuePanel from "@/components/construction/OfflineQueuePanel";
import { useOffline } from "@/context/OfflineContext";
import { OFFLINE } from "@/constants/testIds";

/**
 * Spanduk keadaan jaringan (Fase 35) — muncul HANYA bila ada yang perlu diketahui:
 * sedang offline, ada pekerjaan menunggu terkirim, atau ada yang ditolak server.
 * Tujuannya menghilangkan rasa "pekerjaan saya hilang" saat sinyal lapangan mati.
 *
 * Antrean bisa dibuka DARI HALAMAN MANA SAJA lewat tombol "Lihat antrean": antrean itu
 * milik perangkat, bukan milik satu halaman. Dulu daftarnya hanya ada di tab Papan Mandor,
 * sehingga saat offline (halaman lain gagal memuat) mandor tidak bisa memeriksa atau
 * mencoba mengirim ulang pekerjaannya.
 */
export default function OfflineBanner() {
  const { online, pending, rejected, jobs, flush } = useOffline();
  const [open, setOpen] = useState(false);
  if (online && !pending && !rejected) return null;

  const tone = !online
    ? "border-amber-300 bg-amber-50 text-amber-900"
    : rejected
      ? "border-rose-300 bg-rose-50 text-rose-900"
      : "border-sky-300 bg-sky-50 text-sky-900";

  return (
    <div className={`border-b ${tone}`}>
      <div data-testid={OFFLINE.banner} data-online={online ? "1" : "0"}
        className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-xs md:px-8">
        <p className="flex flex-wrap items-center gap-2">
          {online ? <UploadCloud className="h-4 w-4" /> : <CloudOff className="h-4 w-4" />}
          <span>
            {!online ? (
              <>
                <b>Mode offline.</b> Pekerjaan tetap bisa diajukan — tersimpan di perangkat dan
                terkirim otomatis begitu sinyal kembali.
              </>
            ) : rejected ? (
              <>
                <b>{rejected} pengajuan ditolak server.</b> Buka antrean untuk melihat
                alasannya — bukti fotonya masih tersimpan.
              </>
            ) : (
              <><b>Mengirim pekerjaan tersimpan…</b> Jangan tutup aplikasi dulu.</>
            )}
          </span>
          {pending ? (
            <span data-testid={OFFLINE.pending}
              className="rounded-full border border-current/30 bg-white/70 px-2 py-0.5 font-semibold">
              {pending} menunggu terkirim
            </span>
          ) : null}
        </p>
        <div className="flex items-center gap-2">
          {jobs.length ? (
            <Button size="sm" variant="ghost" data-testid={OFFLINE.queueToggle}
              onClick={() => setOpen((v) => !v)}>
              {open ? <ChevronUp className="mr-1 h-3.5 w-3.5" />
                : <ChevronDown className="mr-1 h-3.5 w-3.5" />}
              {open ? "Sembunyikan antrean" : `Lihat antrean (${jobs.length})`}
            </Button>
          ) : null}
          {online && (pending || rejected) ? (
            <Button size="sm" variant="outline" data-testid={OFFLINE.flush}
              onClick={() => flush()}>
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Kirim sekarang
            </Button>
          ) : null}
        </div>
      </div>
      {open ? (
        <div className="px-4 pb-3 md:px-8">
          <OfflineQueuePanel />
        </div>
      ) : null}
    </div>
  );
}
