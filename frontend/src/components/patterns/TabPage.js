import React, { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Clock } from "lucide-react";

import { cn } from "@/lib/utils";
import { TABPAGE } from "@/constants/testIds";

/**
 * TabPage — layout halaman kanonik dengan tab yang SINKRON KE URL (`?tab=`).
 *
 * Kenapa sinkron ke URL: tab yang hanya hidup di state tidak bisa dibagikan ("lihat tab
 * Dokumen lead ini"), hilang saat halaman dimuat ulang, dan membuat tombol Kembali browser
 * terasa rusak.
 *
 * tabs: [{ key, label, icon?, badge?, content, soon? }]
 *   `soon: "belum masuk rencana kerja berjalan"` → tab tetap TERLIHAT (supaya pemakai tahu
 *   peta jalannya) tetapi isinya menjelaskan dengan jujur bahwa datanya belum ada, bukan
 *   tabel kosong palsu.
 *
 *   ATURAN PENTING (pelajaran nyata): `soon` TIDAK BOLEH berisi NOMOR FASE. Urutan
 *   pengerjaan pernah berubah, sehingga tab yang berjanji "dijadwalkan Fase 43" masih mati
 *   lama setelah Fase 43 selesai — pemakai membaca janji yang tidak pernah datang. Tulis
 *   NAMA pekerjaannya ("kontrak formal & rincian biaya per komponen"), bukan nomornya.
 */
/**
 * Penanda tab, dari LUAR ke DALAM. `hub` dipakai halaman hub (mis. `/build`), `tab` dipakai
 * halaman di dalamnya. Urutan ini yang membuat aturan reset di `go()` bisa jujur tanpa
 * TabPage perlu tahu siapa induknya.
 */
const TAB_MARKERS = ["hub", "tab"];

export default function TabPage({ tabs = [], header = null, paramKey = "tab", testId }) {
  const [params, setParams] = useSearchParams();
  const list = tabs.filter(Boolean);
  const active = useMemo(() => {
    const want = params.get(paramKey);
    return list.find((t) => t.key === want) || list[0];
  }, [params, paramKey, list]);

  /**
   * Pindah tab = MULAI BERSIH.
   *
   * Cacat nyata yang ditutup (ditemukan saat uji browser Fase 40c): filter satu tab bocor ke
   * tab lain karena query lama dibawa apa adanya. Contohnya `project_id` yang ditulis tab
   * "Kalender Jadwal" ikut terbaca tab "Papan Unit" sebagai FILTER PROYEK, sehingga pemakai
   * melihat chip filter yang tidak pernah ia pilih (dan angka yang tampak "kurang" tanpa
   * sebab). Karena itu seluruh query dibuang saat berpindah tab — kecuali penanda tab yang
   * lebih LUAR (mis. `hub`), yang kalau ikut terhapus akan menendang pemakai keluar dari hub.
   */
  const go = (key) => {
    const next = new URLSearchParams();
    for (const marker of TAB_MARKERS) {
      if (marker === paramKey) break;          // penanda yang lebih dalam TIDAK dipertahankan
      const value = params.get(marker);
      if (value) next.set(marker, value);
    }
    next.set(paramKey, key);
    setParams(next, { replace: false });
  };

  return (
    <div data-testid={testId || TABPAGE.root} className="space-y-4">
      {header}
      <div data-testid={TABPAGE.tabs} role="tablist"
        className="flex flex-wrap gap-1 rounded-xl border border-border bg-[hsl(var(--surface-sunken))] p-1.5 shadow-[var(--shadow-card)]">
        {list.map((t) => {
          const on = active?.key === t.key;
          const Icon = t.icon;
          return (
            <button key={t.key} type="button" role="tab" aria-selected={on}
              data-testid={`${TABPAGE.tab}-${t.key}`} data-active={on ? "true" : "false"}
              onClick={() => go(t.key)}
              className={cn("inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm",
                "transition-[background-color,color,box-shadow] duration-150",
                on ? "bg-primary font-semibold text-primary-foreground shadow-sm"
                  : "font-medium text-muted-foreground hover:bg-card hover:text-foreground hover:shadow-sm")}>
              {Icon ? <Icon className="h-4 w-4" /> : null}
              {t.label}
              {t.badge !== undefined && t.badge !== null ? (
                <span className={cn("rounded px-1 text-xs tabular-nums",
                  on ? "bg-primary-foreground/20" : "bg-secondary")}>{t.badge}</span>
              ) : null}
              {t.soon ? (
                <span className="rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-800">
                  {t.soon}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div data-testid={TABPAGE.panel} data-tab={active?.key} role="tabpanel">
        {active?.soon ? (
          <div data-testid={TABPAGE.soon}
            className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
            <p className="flex items-center gap-2 font-medium">
              <Clock className="h-4 w-4" /> Belum aktif — {active.soon}
            </p>
            <p className="mt-1.5">
              {active.soonNote || `Data untuk “${active.label}” belum dibuat sistem, jadi tab ini `
                + "sengaja tidak menampilkan angka apa pun (lebih baik kosong-jujur daripada "
                + "tabel palsu). Tab ini tetap terlihat agar peta jalannya jelas."}
            </p>
          </div>
        ) : active?.content}
      </div>
    </div>
  );
}
