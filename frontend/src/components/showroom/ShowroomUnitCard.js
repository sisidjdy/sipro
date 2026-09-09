import React from "react";
import { Compass, Ruler, Tag } from "lucide-react";

import { SALES_COLORS } from "@/components/siteplan/planStyles";
import { formatIDR } from "@/utils/formatters";
import { SHOWROOM } from "@/constants/testIds";

/**
 * Kartu kavling di halaman publik. Label status/tipe/orientasi diambil dari SSOT yang
 * dikirim backend (`labels`) — tidak ada kamus enum yang di-hardcode di frontend.
 */
export default function ShowroomUnitCard({ unit, labels = {}, onOpen }) {
  const tone = SALES_COLORS[unit.status] || SALES_COLORS.available;
  const statusLabel = labels.unit_status?.[unit.status] || unit.status;
  const orientation = unit.orientation ? (labels.unit_orientation?.[unit.orientation] || unit.orientation) : null;

  return (
    <button type="button" data-testid={SHOWROOM.unitCard} data-unit-code={unit.code}
      data-unit-status={unit.status} onClick={() => onOpen(unit)}
      className="group rounded-xl border bg-card p-3 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-heading text-base font-bold leading-none">{unit.code}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {labels.unit_type?.[unit.type] || unit.type || "-"}
          </p>
        </div>
        <span className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
          style={{ backgroundColor: tone.fill, color: tone.text }}>
          {statusLabel}
        </span>
      </div>

      <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Ruler className="h-3.5 w-3.5" />
        {unit.luas_bangunan ? `${unit.luas_bangunan} m² bangunan · ` : ""}{unit.luas_tanah || 0} m² tanah
      </p>
      {orientation ? (
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Compass className="h-3.5 w-3.5" /> Hadap {orientation}{unit.corner ? " · hook" : ""}
        </p>
      ) : null}

      <p className="mt-2 flex items-center gap-1.5 text-sm font-semibold tabular-nums">
        <Tag className="h-3.5 w-3.5 text-primary" />
        {unit.price === null || unit.price === undefined
          ? "Hubungi marketing" : formatIDR(unit.price)}
      </p>
    </button>
  );
}
