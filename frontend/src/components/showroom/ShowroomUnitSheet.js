import React from "react";
import { MessageCircle } from "lucide-react";

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { SALES_COLORS } from "@/components/siteplan/planStyles";
import { formatIDR } from "@/utils/formatters";
import { SHOWROOM } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}

/**
 * Detail kavling versi PUBLIK: hanya spesifikasi & status. Tidak ada nama pembeli,
 * nilai transaksi, progres pembayaran, atau riwayat internal — backend memang tidak
 * mengirimkannya, jadi tidak ada data sensitif yang "disembunyikan lewat CSS".
 */
export default function ShowroomUnitSheet({ unit, labels = {}, onClose, onAsk }) {
  if (!unit) return null;
  const tone = SALES_COLORS[unit.status] || SALES_COLORS.available;
  const statusLabel = labels.unit_status?.[unit.status] || unit.status;
  const orientation = unit.orientation
    ? (labels.unit_orientation?.[unit.orientation] || unit.orientation) : "-";
  const perM2 = unit.price && unit.luas_tanah ? Math.round(unit.price / unit.luas_tanah) : 0;

  return (
    <Sheet open onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent data-testid={SHOWROOM.unitSheet} className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="flex flex-wrap items-center gap-2">
            Kavling {unit.code}
            <span className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              style={{ backgroundColor: tone.fill, color: tone.text }}>{statusLabel}</span>
          </SheetTitle>
          <SheetDescription>
            {labels.unit_type?.[unit.type] || unit.type || "-"}
            {unit.corner ? " · kavling hook (sudut)" : ""}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <Row label="Blok" value={unit.block || "-"} />
          <Row label="Luas tanah" value={`${unit.luas_tanah || 0} m²`} />
          <Row label="Luas bangunan" value={`${unit.luas_bangunan || 0} m²`} />
          <Row label="Orientasi" value={orientation} />
          <Row label="Harga"
            value={unit.price === null || unit.price === undefined
              ? "Hubungi marketing" : formatIDR(unit.price)} />
          {perM2 ? <Row label="Harga per m² tanah" value={formatIDR(perM2)} /> : null}
          <Row label="Ketersediaan" value={unit.available ? "Masih tersedia" : "Sudah dipesan/terjual"} />
        </div>

        <Button className="mt-4 w-full" data-testid={SHOWROOM.unitSheetAsk} onClick={() => onAsk(unit)}>
          <MessageCircle className="mr-1.5 h-4 w-4" />
          {unit.available ? `Tanya kavling ${unit.code}` : "Tanya kavling serupa"}
        </Button>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Ketersediaan & harga dapat berubah sewaktu-waktu; konfirmasi akhir oleh tim marketing.
        </p>
      </SheetContent>
    </Sheet>
  );
}
