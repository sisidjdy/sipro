import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { KIND_STYLE } from "@/components/siteplan/planStyles";
import { lotStyle } from "@/components/siteplan/studio/exportPng";
import StudioLegend from "@/components/siteplan/studio/StudioLegend";
import { photoSrc } from "@/utils/photoSrc";
import { STUDIO } from "@/constants/testIds";

const ORDER = { boundary: 0, green: 1, water: 2, road: 3, facility: 4, lot: 5 };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const parsePts = (g) => String(g?.points || "").trim().split(/\s+/).filter(Boolean)
  .map((p) => p.split(",").map(Number));

/**
 * Kanvas Studio — SVG dengan zoom/pan, gambar latar (tracing), klik bentuk, dan mode
 * gambar poligon (klik titik demi titik, klik ganda / tombol Selesai untuk menutup).
 */
export default function StudioCanvas({ plan, unitsById, selectedId, tool, onShapeClick, onDrawDone, onVertexMove, bgOpacity = 1, colorMode = "mapping", palette }) {
  const wrapRef = useRef(null);
  const [view, setView] = useState({ k: 1, tx: 0, ty: 0 });
  const [draft, setDraft] = useState([]);
  const [cursor, setCursor] = useState(null);
  const drag = useRef(null);
  const vtx = useRef(null);
  const [editPts, setEditPts] = useState(null);

  useEffect(() => { setEditPts(null); }, [selectedId, plan?.updated_at]);

  const [vx, vy, vw, vh] = useMemo(() => {
    const p = String(plan?.view_box || "0 0 1600 1000").split(/[\s,]+/).map(Number);
    return p.length === 4 && p.every((n) => !Number.isNaN(n)) ? p : [0, 0, 1600, 1000];
  }, [plan?.view_box]);

  useEffect(() => { setView({ k: 1, tx: 0, ty: 0 }); }, [plan?.view_box]);
  useEffect(() => { if (tool !== "draw") setDraft([]); }, [tool]);

  const shapes = useMemo(() => [...(plan?.shapes || [])]
    .sort((a, b) => (ORDER[a.kind] ?? 9) - (ORDER[b.kind] ?? 9)), [plan?.shapes]);

  const toPlan = useCallback((clientX, clientY) => {
    const r = wrapRef.current.getBoundingClientRect();
    const px = vx + ((clientX - r.left) / r.width) * vw;
    const py = vy + ((clientY - r.top) / r.height) * vh;
    return [(px - view.tx) / view.k, (py - view.ty) / view.k];
  }, [vx, vy, vw, vh, view]);

  const zoomBy = useCallback((factor, cx, cy) => {
    setView((v) => {
      const k = clamp(v.k * factor, 0.3, 12);
      const px = cx ?? vx + vw / 2; const py = cy ?? vy + vh / 2;
      return { k, tx: px - (px - v.tx) * (k / v.k), ty: py - (py - v.ty) * (k / v.k) };
    });
  }, [vx, vy, vw, vh]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15, vx + ((e.clientX - r.left) / r.width) * vw,
        vy + ((e.clientY - r.top) / r.height) * vh);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomBy, vx, vy, vw, vh]);

  const finishDraw = useCallback(() => {
    if (draft.length >= 3) onDrawDone?.(draft.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]));
    setDraft([]);
  }, [draft, onDrawDone]);

  useEffect(() => {
    const onKey = (e) => {
      if (tool !== "draw") return;
      if (e.key === "Enter") finishDraw();
      if (e.key === "Escape") setDraft([]);
      if (e.key === "Backspace") setDraft((d) => d.slice(0, -1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tool, finishDraw]);

  const onPointerDown = (e) => {
    if (e.button !== 0 || vtx.current) return;
    const r = wrapRef.current.getBoundingClientRect();
    drag.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, w: r.width, h: r.height, moved: false };
  };
  const onPointerMove = (e) => {
    if (tool === "draw") setCursor(toPlan(e.clientX, e.clientY));
    if (vtx.current) {
      const [x, y] = toPlan(e.clientX, e.clientY);
      setEditPts((pts) => pts.map((p, i) => (i === vtx.current.index ? [x, y] : p)));
      return;
    }
    if (!drag.current) return;
    const d = drag.current;
    if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) d.moved = true;
    if (!d.moved) return;
    setView((v) => ({ ...v, tx: d.tx + ((e.clientX - d.x) / d.w) * vw, ty: d.ty + ((e.clientY - d.y) / d.h) * vh }));
  };
  const onPointerUp = (e) => {
    if (vtx.current) {
      const sid = vtx.current.sid;
      vtx.current = null;
      if (editPts && editPts.length >= 3) onVertexMove?.(sid, editPts.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]));
      return;
    }
    const d = drag.current;
    drag.current = null;
    if (tool === "draw" && d && !d.moved) {
      const pt = toPlan(e.clientX, e.clientY);
      const first = draft[0];
      if (first && draft.length >= 3 && Math.hypot(first[0] - pt[0], first[1] - pt[1]) * view.k < vw * 0.012) {
        finishDraw();
      } else setDraft((cur) => [...cur, pt]);
    }
  };

  const bg = plan?.background;
  const labelSize = Math.max(8, 18 / view.k);
  const cursorCls = tool === "draw" ? "cursor-crosshair" : "cursor-grab active:cursor-grabbing";

  return (
    <div className="relative h-full">
      <div ref={wrapRef} data-testid={STUDIO.canvas} data-tool={tool}
        className={`relative h-full w-full overflow-hidden rounded-xl border bg-[#1f2933] ${cursorCls}`}
        style={{ touchAction: "none", backgroundImage: "radial-gradient(#334155 0.8px, transparent 0.8px)", backgroundSize: "18px 18px" }}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
        onPointerLeave={() => { drag.current = null; setCursor(null); }}
        onDoubleClick={() => tool === "draw" && finishDraw()}>
        <svg viewBox={`${vx} ${vy} ${vw} ${vh}`} className="h-full w-full select-none" role="img" aria-label="Kanvas studio site plan">
          <g transform={`translate(${view.tx} ${view.ty}) scale(${view.k})`}>
            <rect x={vx} y={vy} width={vw} height={vh} fill={bg ? "#0f172a" : "#f4f8f3"} />
            {bg?.file_id ? (
              <image href={photoSrc({ file_id: bg.file_id })} x={0} y={0} width={bg.width} height={bg.height}
                opacity={bgOpacity} preserveAspectRatio="none" style={{ pointerEvents: "none" }} />
            ) : null}
            {shapes.map((s) => {
              const isLot = s.kind === "lot";
              const u = isLot ? unitsById[s.unit_id] : null;
              const st = isLot ? lotStyle(s, u, colorMode, palette) : (KIND_STYLE[s.kind] || KIND_STYLE.facility);
              const active = s.shape_id === selectedId;
              const g = active && editPts ? { type: "polygon", points: editPts.map((p) => p.join(",")).join(" ") } : (s.geom || {});
              const props = {
                fill: st.fill, fillOpacity: bg ? 0.55 : 0.9, stroke: active ? "#2563eb" : st.stroke,
                strokeWidth: active ? Math.max(3, st.strokeWidth || 0) : (isLot ? (st.strokeWidth || 1.4) : (st.width || 1)), strokeDasharray: st.dash || (isLot && !u ? "5 3" : undefined),
                vectorEffect: "non-scaling-stroke",
              };
              return (
                <g key={s.shape_id} data-testid={STUDIO.shape} data-shape-id={s.shape_id} data-kind={s.kind}
                  data-mapped={u ? "1" : "0"} data-selected={active ? "1" : "0"}
                  style={{ cursor: tool === "draw" ? "crosshair" : "pointer" }}
                  onClick={(e) => { if (tool !== "draw") { e.stopPropagation(); onShapeClick?.(s); } }}>
                  {g.type === "path" ? <path d={g.d} {...props} /> : <polygon points={g.points} {...props} />}
                  {s.centroid && (isLot || s.label) && s.kind !== "boundary" ? (
                    <text x={s.centroid.x} y={s.centroid.y + labelSize * (st.sub ? 0 : 0.35)} textAnchor="middle"
                      fontSize={isLot ? labelSize : labelSize * 0.7} fontWeight={isLot ? 700 : 500}
                      fill={isLot ? st.text : "#475569"} style={{ pointerEvents: "none" }}>
                      {u ? u.code : (s.label || "?")}
                      {st.sub ? <tspan x={s.centroid.x} dy={labelSize * 0.95} fontSize={labelSize * 0.7} fontWeight={500}>{st.sub}</tspan> : null}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {tool === "select" && selectedId ? (() => {
              const sel = shapes.find((x) => x.shape_id === selectedId);
              if (!sel || sel.geom?.type !== "polygon") return null;
              const pts = editPts || parsePts(sel.geom);
              return pts.map((p, i) => (
                <circle key={i} data-testid={STUDIO.vertex} cx={p[0]} cy={p[1]} r={Math.max(3.5, 7 / view.k)}
                  fill="#fff" stroke="#2563eb" strokeWidth={2} vectorEffect="non-scaling-stroke"
                  style={{ cursor: "move" }}
                  onPointerDown={(e) => { e.stopPropagation(); vtx.current = { sid: selectedId, index: i }; setEditPts(pts); }} />
              ));
            })() : null}
            {draft.length ? (
              <g>
                <polyline points={[...draft, ...(cursor ? [cursor] : [])].map((p) => p.join(",")).join(" ")}
                  fill="rgba(37,99,235,0.18)" stroke="#2563eb" strokeWidth={2} vectorEffect="non-scaling-stroke" />
                {draft.map((p, i) => (
                  <circle key={i} cx={p[0]} cy={p[1]} r={Math.max(3, 6 / view.k)} fill={i === 0 ? "#f59e0b" : "#2563eb"} stroke="#fff" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
                ))}
              </g>
            ) : null}
          </g>
        </svg>

        <StudioLegend colorMode={colorMode} shapes={plan?.shapes || []} unitsById={unitsById} palette={palette} />
        {tool === "select" && selectedId && !editPts ? (
          <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-slate-800/85 px-3 py-1 text-[11px] text-white shadow">
            Seret titik sudut biru untuk memperbaiki bentuk · Ctrl+Z membatalkan
          </div>
        ) : null}
        {tool === "draw" ? (
          <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-blue-600/90 px-3 py-1 text-xs font-medium text-white shadow">
            Mode gambar: klik titik sudut kavling · {draft.length} titik · Enter/klik ganda selesai · Esc batal
          </div>
        ) : null}
        {draft.length >= 3 ? (
          <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-2">
            <button type="button" data-testid={STUDIO.drawFinish} onClick={finishDraw}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow hover:bg-emerald-700">Selesai poligon</button>
            <button type="button" data-testid={STUDIO.drawCancel} onClick={() => setDraft([])}
              className="rounded-md bg-white px-3 py-1.5 text-xs font-semibold shadow hover:bg-slate-100">Batal</button>
          </div>
        ) : null}
      </div>
      <div className="absolute right-3 top-3 flex flex-col gap-1.5">
        {[["+", 1.3, STUDIO.zoomIn, "Perbesar"], ["−", 1 / 1.3, STUDIO.zoomOut, "Perkecil"]].map(([t, f, id, label]) => (
          <button key={id} type="button" data-testid={id} aria-label={label} onClick={() => zoomBy(f)}
            className="h-8 w-8 rounded-md border bg-white text-lg font-semibold shadow-sm hover:bg-secondary">{t}</button>
        ))}
        <button type="button" data-testid={STUDIO.zoomReset} aria-label="Reset tampilan" onClick={() => setView({ k: 1, tx: 0, ty: 0 })}
          className="h-8 w-8 rounded-md border bg-white text-[9px] font-semibold shadow-sm hover:bg-secondary">FIT</button>
      </div>
    </div>
  );
}
