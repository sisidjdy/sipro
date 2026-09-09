import React, { useState } from "react";
import ClosingChecklistPanel from "@/components/gl/ClosingChecklistPanel";
import YearClosingPanel from "@/components/gl/YearClosingPanel";

/**
 * Tab "Penutupan Buku" (Fase 49A + 49B) di halaman Buku Besar & Jurnal.
 *
 * Dua hal digabung SENGAJA: menutup bulan dan menutup tahun adalah satu pekerjaan berurutan
 * (tahun tidak boleh ditutup sebelum bulannya bersih). Bila periode ditutup/dibuka, panel
 * tahun ikut dimuat ulang supaya angka "laba tahun berjalan" tidak basi di layar.
 */
export default function BookClosingTab() {
  const [nonce, setNonce] = useState(0);
  const bump = () => setNonce((v) => v + 1);
  return (
    <div className="space-y-6">
      <ClosingChecklistPanel onChanged={bump} />
      <div className="border-t pt-5">
        <YearClosingPanel key={`year_${nonce}`} onChanged={bump} />
      </div>
    </div>
  );
}
