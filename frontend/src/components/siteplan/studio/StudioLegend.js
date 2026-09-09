import React from "react";
import { legendItems } from "@/components/siteplan/studio/studioPalette";
import { STUDIO } from "@/constants/testIds";

/** Legenda kanvas — mengikuti mode warna & palet organisasi; mode gabungan menampilkan dua kelompok. */
export default function StudioLegend({ colorMode, shapes, unitsById, palette }) {
  const lots = shapes.filter((s) => s.kind === "lot");
  const items = legendItems(colorMode, lots, unitsById, palette);
  const groups = colorMode === "dual" ? items : [{ items }];
  return (
    <div data-testid={STUDIO.legend} className="pointer-events-none absolute bottom-3 left-3 max-w-[85%] space-y-1 rounded-lg bg-white/92 px-2.5 py-1.5 text-[11px] shadow backdrop-blur">
      {groups.map((g, gi) => (
        <div key={g.group || gi} className="flex flex-wrap items-center gap-1.5">
          {g.group ? <span className="mr-1 font-semibold text-slate-600">{g.group}:</span> : null}
          {g.items.map((it) => (
            <span key={it.key} data-testid={`${STUDIO.legendItem}-${it.key}`} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-sm"
                style={g.asStroke ? { border: `2.5px solid ${it.stroke}`, background: "#fff" } : { background: it.fill, border: `1px solid ${it.stroke}` }} />
              {it.label} <strong>{it.n}</strong>
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}
