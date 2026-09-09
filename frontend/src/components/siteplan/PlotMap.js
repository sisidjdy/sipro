import React from "react";
import { cn } from "@/lib/utils";
import { PLOT_TONE } from "@/components/siteplan/PlanLegend";
import { SITE_PLAN } from "@/constants/testIds";

const compactIDR = (v) => {
  const n = Number(v) || 0;
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(n % 1_000_000_000 ? 1 : 0)} M`;
  if (n >= 1_000_000) return `${Math.round(n / 1_000_000)} jt`;
  return String(n);
};

/**
 * PlotMap — peta kavling interaktif (blok dipisah "jalan").
 *
 * Posisi tiap plot berasal dari backend (`/api/site-plan/{project_id}`): dipakai
 * posisi eksplisit `unit.plan` bila ada, jika tidak backend menghitung auto-layout
 * deterministik sehingga peta selalu tampil tanpa perlu setup manual.
 */
export default function PlotMap({
  canvas, blocks = [], units = [], zoom = 1, selectedId, isMatch, onSelect,
}) {
  const width = canvas?.width || 800;
  const height = canvas?.height || 400;

  return (
    <div className="relative overflow-auto rounded-xl border bg-[hsl(150_18%_95%)] p-0 shadow-inner"
      style={{ maxHeight: 620 }} data-testid={SITE_PLAN.canvas}>
      <div style={{ width: width * zoom, height: height * zoom }} className="relative mx-auto">
        <div className="absolute left-0 top-0 origin-top-left"
          style={{ width, height, transform: `scale(${zoom})` }}>
          {/* Jalan (grid halus) */}
          <div className="absolute inset-0"
            style={{
              backgroundImage:
                "repeating-linear-gradient(0deg, hsl(150 12% 88%) 0 1px, transparent 1px 40px), repeating-linear-gradient(90deg, hsl(150 12% 88%) 0 1px, transparent 1px 40px)",
            }} />

          {/* Blok */}
          {blocks.map((b) => (
            <div key={b.name} data-testid={SITE_PLAN.block} data-block-name={b.name}
              className="absolute rounded-xl border border-dashed border-emerald-900/15 bg-white/55"
              style={{ left: b.x - 14, top: b.y - 6, width: width - (b.x - 14) * 2, height: b.height + 12 }}>
              <span className="absolute -top-0.5 left-3 top-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-900/70">
                Blok {b.name} · {b.count} kavling
              </span>
            </div>
          ))}

          {/* Kavling */}
          {units.map((u) => {
            const tone = PLOT_TONE[u.status] || PLOT_TONE.available;
            const match = isMatch ? isMatch(u) : true;
            const active = selectedId === u.id;
            return (
              <button key={u.id} type="button"
                data-testid={SITE_PLAN.plot}
                data-unit-code={u.code}
                data-unit-status={u.status}
                aria-label={`Kavling ${u.code} — ${tone.label}`}
                title={`${u.code} · ${u.type || "-"} · ${u.status}`}
                onClick={() => onSelect && onSelect(u)}
                className={cn(
                  "absolute flex flex-col justify-between rounded-lg border-2 p-1.5 text-left shadow-sm transition-all",
                  tone.tile,
                  match ? "opacity-100" : "opacity-20 saturate-0",
                  active ? "ring-2 ring-primary ring-offset-1" : "hover:-translate-y-0.5 hover:shadow-md",
                )}
                style={{ left: u.x, top: u.y, width: u.w, height: u.h }}>
                <span className="flex items-start justify-between gap-1">
                  <span className="font-heading text-[13px] font-bold leading-none">{u.code}</span>
                  {u.corner ? (
                    <span className="rounded bg-white/70 px-1 text-[9px] font-semibold uppercase">hook</span>
                  ) : null}
                </span>
                <span className="text-[10px] leading-tight opacity-80">
                  {u.luas_bangunan ? `${u.luas_bangunan}/${u.luas_tanah || 0} m²` : `${u.luas_tanah || 0} m² tanah`}
                </span>
                <span className="text-[11px] font-semibold tabular-nums leading-none">
                  {compactIDR(u.price)}
                </span>
                {u.status !== "available" ? (
                  <span className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-white/70">
                    <span className="block h-full rounded-full bg-current opacity-60"
                      style={{ width: `${u.construction_progress || 0}%` }} />
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
