import React from "react";

import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import UnitScheduleView from "@/components/build/UnitScheduleView";
import { BUILD } from "@/constants/testIds";

/**
 * Drawer drill-cepat jadwal unit (dipakai dari papan monitoring & kalender).
 *
 * Fase 46: isinya sekarang komponen yang SAMA dengan Unit 360 → tab Pembangunan
 * (`UnitScheduleView`). Sebelumnya seluruh logika ada di dalam drawer, sehingga halaman
 * unit tidak mungkin punya kemampuan yang sama tanpa menyalin ±200 baris — dan salinan
 * berarti dua perilaku yang bisa berbeda diam-diam.
 */
export default function UnitScheduleSheet({ unitId, unitCode, open, onOpenChange, onChanged }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={BUILD.sheet}
        className="w-full overflow-y-auto bg-background sm:max-w-2xl">
        <SheetHeader className="sticky top-0 z-10 bg-background pb-2">
          <SheetTitle>Jadwal unit {unitCode || "—"}</SheetTitle>
          <SheetDescription>
            Minggu → langkah kerja, gerbang bukti, dan aksi verifikasi. Buka Unit 360 untuk
            melihatnya bersama mutu, izin, dan kesiapan mulai bangun.
          </SheetDescription>
        </SheetHeader>
        {open ? (
          <UnitScheduleView unitId={unitId} onChanged={onChanged} />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
