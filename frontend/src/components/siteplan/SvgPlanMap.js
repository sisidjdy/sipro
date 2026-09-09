import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { KIND_STYLE, shortIDR, unitStyle } from "@/components/siteplan/planStyles";
import { SITE_PLAN } from "@/constants/testIds";

const ORDER = { boundary: 0, green: 1, water: 2, road: 3, facility: 4, lot: 5 };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function Shape({ shape, style, extra = {}, className }) {
  const g = shape.geom || {};
  if (g.type === "path") return <path d={g.d} {...style} {...extra} className={className} />;
  return <polygon points={g.points} {...style} {...extra} className={className} />;
}

/** Teks kedua di dalam kavling, mengikuti mode warna aktif (hanya saat zoom dekat). */
function subLabel(unit, mode) {
  if (mode === "build") return `${Number(unit.construction_progress || 0)}%`;
  if (mode === "price") return shortIDR(unit.price);
  if (mode === "dom") {
    if (unit.dom_open === false) return "laku";
    return unit.days_on_market === null || unit.days_on_market === undefined
      ? "" : `${unit.days_on_market} hr`;
  }
  return "";
}

/**
 * SvgPlanMap — peta site plan berbasis SVG asli (Fase 28).
 *
 * Menggantikan grid kotak: geometri (kavling, jalan, taman, danau, fasilitas) datang dari
 * `site_plans.shapes` — hasil generator realistis ATAU parsing SVG arsitek. Markup SVG
 * pihak ketiga TIDAK disuntikkan; hanya atribut geometri (`d`/`points`) yang dirender,
 * jadi tidak ada celah skrip.
 *
 * Interaksi: geser (drag), zoom (roda/tombol), **pinch 2 jari** di layar sentuh (Fase 28b),
 * sorot (hover) -> tooltip, klik -> kartu ringkas, dan mini-map penunjuk posisi.
 */
export default function SvgPlanMap({
  viewBox, shapes = [], unitsById = {}, mode = "sales", selectedId, isMatch,
  onSelect, onHover, showLabels = true, fullscreen = false, resetKey = 0, scales,
  height, emphasizeIds = [], background = null,
}) {
  const wrapRef = useRef(null);
  const [view, setView] = useState({ k: 1, tx: 0, ty: 0 });
  const drag = useRef(null);
  const ptrs = useRef(new Map());
  const pinch = useRef(null);

  const [vx, vy, vw, vh] = useMemo(() => {
    const parts = String(viewBox || "0 0 1600 1000").split(/[\s,]+/).map(Number);
    return parts.length === 4 && parts.every((n) => !Number.isNaN(n)) ? parts : [0, 0, 1600, 1000];
  }, [viewBox]);

  useEffect(() => { setView({ k: 1, tx: 0, ty: 0 }); }, [resetKey, viewBox]);

  const sorted = useMemo(
    () => [...shapes].sort((a, b) => (ORDER[a.kind] ?? 9) - (ORDER[b.kind] ?? 9)), [shapes]);

  const zoomBy = useCallback((factor, cx, cy) => {
    setView((v) => {
      const k = clamp(v.k * factor, 0.6, 9);
      const px = cx ?? vx + vw / 2;
      const py = cy ?? vy + vh / 2;
      return { k, tx: px - (px - v.tx) * (k / v.k), ty: py - (py - v.ty) * (k / v.k) };
    });
  }, [vx, vy, vw, vh]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const px = vx + ((e.clientX - r.left) / r.width) * vw;
      const py = vy + ((e.clientY - r.top) / r.height) * vh;
      zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15, px, py);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomBy, vx, vy, vw, vh]);

  const toPlan = (clientX, clientY) => {
    const r = wrapRef.current.getBoundingClientRect();
    return [vx + ((clientX - r.left) / r.width) * vw, vy + ((clientY - r.top) / r.height) * vh];
  };

  const onPointerDown = (e) => {
    ptrs.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (ptrs.current.size === 2) {
      // Mulai pinch: simpan jarak & transform awal supaya skala mengikuti rasio jari
      // (bukan akumulasi delta) sehingga tidak "melompat" saat jari bergeser.
      const [a, b] = [...ptrs.current.values()];
      pinch.current = { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, ...view };
      drag.current = null;
      return;
    }
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const r = wrapRef.current.getBoundingClientRect();
    drag.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, w: r.width, h: r.height };
  };

  const onPointerMove = (e) => {
    if (ptrs.current.has(e.pointerId)) ptrs.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (ptrs.current.size >= 2 && pinch.current) {
      const [a, b] = [...ptrs.current.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      const start = pinch.current;
      const k = clamp(start.k * (dist / start.dist), 0.6, 9);
      const [cx, cy] = toPlan((a.x + b.x) / 2, (a.y + b.y) / 2);
      const kk = k / start.k;
      setView({ k, tx: cx - (cx - start.tx) * kk, ty: cy - (cy - start.ty) * kk });
      return;
    }
    if (!drag.current) return;
    const d = drag.current;
    setView((v) => ({
      ...v,
      tx: d.tx + ((e.clientX - d.x) / d.w) * vw,
      ty: d.ty + ((e.clientY - d.y) / d.h) * vh,
    }));
  };

  const onPointerUp = (e) => {
    ptrs.current.delete(e.pointerId);
    if (ptrs.current.size < 2) pinch.current = null;
    drag.current = null;
  };

  const endAll = () => {
    ptrs.current.clear();
    pinch.current = null;
    drag.current = null;
  };

  const labelSize = Math.max(9, 20 / view.k);
  const showText = showLabels && view.k >= 0.9;

  return (
    <div className="relative">
      <div ref={wrapRef} data-testid={SITE_PLAN.canvas} data-plan-mode={mode}
        className="relative w-full cursor-grab overflow-hidden rounded-xl border bg-[#f4f8f3] shadow-inner active:cursor-grabbing"
        style={{ height: height || (fullscreen ? "calc(100vh - 190px)" : 560), touchAction: "none" }}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove}
        onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
        onPointerLeave={() => { endAll(); onHover?.(null); }}>
        <svg viewBox={`${vx} ${vy} ${vw} ${vh}`} className="h-full w-full select-none"
          role="img" aria-label="Peta site plan interaktif">
          <g transform={`translate(${view.tx} ${view.ty}) scale(${view.k})`}>
            {background?.url ? (
              <image data-testid="siteplan-background-image" href={background.url} x={0} y={0}
                width={background.width} height={background.height}
                opacity={background.opacity ?? 1} preserveAspectRatio="none"
                style={{ pointerEvents: "none" }} />
            ) : null}
            {sorted.map((s) => {
              if (s.kind === "lot") return null;
              const st = KIND_STYLE[s.kind] || KIND_STYLE.facility;
              return (
                <g key={s.shape_id}>
                  <Shape shape={s} style={{
                    fill: st.fill, stroke: st.stroke, strokeWidth: st.width,
                    strokeDasharray: st.dash, vectorEffect: "non-scaling-stroke",
                  }} />
                  {showText && s.label && s.centroid && s.kind !== "boundary" ? (
                    <text x={s.centroid.x} y={s.centroid.y} textAnchor="middle"
                      fontSize={Math.max(8, labelSize * 0.62)} fill="#5b6b5b"
                      style={{ pointerEvents: "none", fontWeight: 500 }}>{s.label}</text>
                  ) : null}
                </g>
              );
            })}

            {sorted.filter((s) => s.kind === "lot").map((s) => {
              const u = unitsById[s.unit_id];
              if (!u) {
                return (
                  <Shape key={s.shape_id} shape={s} style={{
                    fill: "#ffffff", stroke: "#cbd5e1", strokeWidth: 1,
                    strokeDasharray: "4 4", vectorEffect: "non-scaling-stroke",
                  }} />
                );
              }
              const st = unitStyle(u, mode, scales);
              const match = isMatch ? isMatch(u) : true;
              const active = selectedId === u.id;
              const mine = emphasizeIds.includes(u.id);
              const sub = subLabel(u, mode);
              return (
                <g key={s.shape_id} data-testid={SITE_PLAN.plot} data-unit-code={u.code}
                  data-unit-status={u.status} data-tone={st.key}
                  data-emphasized={mine ? "1" : undefined}
                  role="button" tabIndex={0}
                  aria-label={`Kavling ${u.code}`}
                  style={{ cursor: "pointer", opacity: match ? 1 : 0.22 }}
                  onMouseEnter={(e) => onHover?.({ unit: u, rect: e.currentTarget.getBoundingClientRect() })}
                  onMouseLeave={() => onHover?.(null)}
                  onClick={(e) => onSelect?.({ unit: u, rect: e.currentTarget.getBoundingClientRect() })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      onSelect?.({ unit: u, rect: e.currentTarget.getBoundingClientRect() });
                    }
                  }}>
                  <Shape shape={s} style={{
                    fill: st.fill, stroke: active ? "#0f172a" : st.stroke,
                    strokeWidth: active ? 3 : 1.6, vectorEffect: "non-scaling-stroke",
                  }} />
                  {/* Kavling yang perlu ditonjolkan (mis. milik pembeli di portal). */}
                  {mine ? (
                    <Shape shape={s} style={{
                      fill: "none", stroke: "#4f46e5", strokeWidth: 4,
                      strokeDasharray: "7 4", vectorEffect: "non-scaling-stroke",
                    }} />
                  ) : null}
                  {showText ? (
                    <text x={s.centroid?.x} y={(s.centroid?.y || 0) + labelSize * 0.32}
                      textAnchor="middle" fontSize={labelSize} fill={st.text}
                      style={{ pointerEvents: "none", fontWeight: 700 }}>{u.code}</text>
                  ) : null}
                  {sub && showText && view.k >= 1.4 ? (
                    <text x={s.centroid?.x} y={(s.centroid?.y || 0) + labelSize * 1.5}
                      textAnchor="middle" fontSize={labelSize * 0.72} fill={st.text}
                      style={{ pointerEvents: "none" }}>
                      {sub}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Mini-map */}
        <div className="pointer-events-none absolute bottom-3 right-3 hidden w-40 rounded-lg border bg-white/90 p-1 shadow-md md:block">
          <svg viewBox={`${vx} ${vy} ${vw} ${vh}`} className="h-20 w-full">
            {sorted.map((s) => {
              const isLot = s.kind === "lot";
              const u = isLot ? unitsById[s.unit_id] : null;
              const st = isLot && u ? unitStyle(u, mode, scales) : (KIND_STYLE[s.kind] || KIND_STYLE.facility);
              return <Shape key={`m-${s.shape_id}`} shape={s}
                style={{ fill: st.fill, stroke: "none" }} />;
            })}
            <rect x={(vx - view.tx) / view.k} y={(vy - view.ty) / view.k}
              width={vw / view.k} height={vh / view.k}
              fill="none" stroke="#0f172a" strokeWidth={vw / 260} />
          </svg>
        </div>

        <p className="pointer-events-none absolute bottom-2 left-3 text-[10px] text-slate-500 md:hidden">
          Cubit dua jari untuk zoom · geser satu jari untuk pindah
        </p>
      </div>

      <div className="absolute left-3 top-3 flex flex-col gap-1.5">
        <button type="button" data-testid={SITE_PLAN.zoomIn} aria-label="Perbesar peta"
          onClick={() => zoomBy(1.3)}
          className="h-8 w-8 rounded-md border bg-white text-lg font-semibold shadow-sm hover:bg-secondary">+</button>
        <button type="button" data-testid={SITE_PLAN.zoomOut} aria-label="Perkecil peta"
          onClick={() => zoomBy(1 / 1.3)}
          className="h-8 w-8 rounded-md border bg-white text-lg font-semibold shadow-sm hover:bg-secondary">−</button>
        <button type="button" data-testid={SITE_PLAN.zoomReset} aria-label="Kembalikan tampilan peta"
          onClick={() => setView({ k: 1, tx: 0, ty: 0 })}
          className="h-8 w-8 rounded-md border bg-white text-[10px] font-semibold shadow-sm hover:bg-secondary">RESET</button>
      </div>
    </div>
  );
}
