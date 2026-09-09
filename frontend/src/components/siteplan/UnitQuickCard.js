import React from "react";
import { ArrowUpRight, CalendarCheck, Ruler, Timer, User2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import RefLabel from "@/components/patterns/RefLabel";
import StatusPill from "@/components/patterns/StatusPill";
import { unitStyle } from "@/components/siteplan/planStyles";
import { formatIDR } from "@/utils/formatters";
import { SITE_PLAN } from "@/constants/testIds";

/** Teks umur listing / lama sampai laku — jujur menyebut mana yang mana. */
function domText(u) {
  const d = u?.days_on_market;
  if (d === null || d === undefined) return null;
  return u.dom_open === false
    ? `Laku setelah ${d} hari dipasarkan`
    : `Dipasarkan ${d} hari`;
}

/**
 * Tingkat 2 dari progressive disclosure: kartu ringkas yang "mengembang" menempel
 * pada kavling yang diklik (tingkat 1 = tooltip hover, tingkat 3 = drawer detail).
 */
export default function UnitQuickCard({
  pick, mode, canReserve, onClose, onDetail, onReserve, containerRect, scales,
}) {
  if (!pick?.unit) return null;
  const u = pick.unit;
  const st = unitStyle(u, mode, scales);
  const r = pick.rect;
  const box = containerRect;
  const width = 268;
  let left = 16;
  let top = 16;
  if (r && box) {
    left = Math.min(Math.max(8, r.left - box.left + r.width / 2 - width / 2), box.width - width - 8);
    top = Math.max(8, r.top - box.top - 12);
  }
  const dom = domText(u);

  return (
    <div data-testid={SITE_PLAN.quickCard}
      className="pointer-events-auto absolute z-20 animate-in fade-in zoom-in-95 duration-150"
      style={{ left, top, width }}>
      <div className="overflow-hidden rounded-xl border bg-card shadow-xl">
        <div className="flex items-start justify-between gap-2 px-3 py-2"
          style={{ backgroundColor: st.fill, borderBottom: `2px solid ${st.stroke}` }}>
          <div>
            <p className="font-heading text-base font-bold leading-none" style={{ color: st.text }}>
              {u.code}
            </p>
            <p className="mt-0.5 text-[11px]" style={{ color: st.text }}>
              {u.type || "-"}{u.corner ? " · kavling hook" : ""}
            </p>
          </div>
          <button type="button" aria-label="Tutup kartu kavling" onClick={onClose}
            className="rounded p-0.5 hover:bg-white/60">
            <X className="h-3.5 w-3.5" style={{ color: st.text }} />
          </button>
        </div>

        <div className="space-y-2 px-3 py-2.5">
          <div data-testid="unit-quick-price-status" className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5">
            <span data-testid="unit-quick-price" className="text-lg font-semibold tabular-nums">{formatIDR(u.price)}</span>
            <StatusPill status={u.status} group="unit_status" />
          </div>
          <div data-testid="unit-quick-dimensions" className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <Ruler className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 leading-relaxed">
            {u.luas_bangunan ? `${u.luas_bangunan} m² bangunan · ` : ""}
            {u.luas_tanah || 0} m² tanah
            {u.orientation ? <span className="inline-block" data-testid="unit-quick-orientation"> · hadap <RefLabel group="unit_orientation" value={u.orientation} /></span> : null}
            </span>
          </div>
          {u.price_per_m2 ? (
            <p className="text-[11px] text-muted-foreground">
              {formatIDR(u.price_per_m2)} per m² tanah
            </p>
          ) : null}
          {dom ? (
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Timer className="h-3.5 w-3.5" /> {dom}
            </p>
          ) : null}
          {u.buyer_name ? (
            <div className="flex items-center gap-1.5 text-xs">
              <User2 className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="truncate">{u.buyer_name}</span>
              {u.legal_stage ? <StatusPill status={u.legal_stage} group="legal_stage" /> : null}
            </div>
          ) : null}

          <div>
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Progres pembangunan</span>
              <span className="font-semibold tabular-nums text-foreground">
                {Number(u.construction_progress || 0)}%
              </span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
              <div className="h-full rounded-full transition-all"
                style={{ width: `${Number(u.construction_progress || 0)}%`,
                  backgroundColor: st.stroke }} />
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5 pt-0.5">
            <Button size="sm" className="flex-1" data-testid={SITE_PLAN.quickDetailBtn}
              onClick={() => onDetail(u)}>
              Detail Lengkap <ArrowUpRight className="ml-1 h-3.5 w-3.5" />
            </Button>
            {canReserve && u.status === "available" ? (
              <Button size="sm" variant="outline" data-testid={SITE_PLAN.quickReserveBtn}
                onClick={() => onReserve(u)}>
                <CalendarCheck className="mr-1 h-3.5 w-3.5" /> Reservasi
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
