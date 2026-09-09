import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, MapPinned } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState, LoadingKpis } from "@/components/patterns/StateViews";
import StudioCanvas from "@/components/siteplan/studio/StudioCanvas";
import StudioToolbar from "@/components/siteplan/studio/StudioToolbar";
import ShapePanel from "@/components/siteplan/studio/ShapePanel";
import UnitsPanel from "@/components/siteplan/studio/UnitsPanel";
import CreateUnitsPanel from "@/components/siteplan/studio/CreateUnitsPanel";
import useStudio from "@/components/siteplan/studio/useStudio";
import { STUDIO } from "@/constants/testIds";

/**
 * Studio Site Plan (Fase 72) — halaman penuh untuk menyiapkan peta proyek:
 * unggah SVG arsitek (label teks terbaca, kavling terdeteksi), atau gambar PNG/JPG lalu
 * gambar poligon kavling di atasnya; petakan ke unit (klik / berurutan) atau lahirkan unit
 * langsung dari bentuk peta.
 */
export default function SitePlanStudioPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const s = useStudio(projectId);
  const [bgOpacity, setBgOpacity] = useState(0.9);
  const [tab, setTab] = useState("shape");

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !["INPUT", "TEXTAREA"].includes(e.target?.tagName)) {
        e.preventDefault(); s.undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s]);

  if (s.loading && !s.data) return <LoadingKpis count={4} />;
  if (s.error) return <ErrorState message={s.error} onRetry={s.load} />;
  const st = s.plan?.stats;

  return (
    <div data-testid={STUDIO.page} className="flex h-[calc(100vh-110px)] min-h-[560px] flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" data-testid={STUDIO.back} aria-label="Kembali ke Site Plan"
            onClick={() => navigate("/site-plan")}><ArrowLeft className="h-4 w-4" /></Button>
          <MapPinned className="h-5 w-5 text-primary" />
          <div>
            <h1 className="page-title">Studio Site Plan</h1>
            <p data-testid={STUDIO.projectName} className="text-xs text-muted-foreground">
              {s.data?.plan?.filename ? `Sumber: ${s.data.plan.filename}` : s.plan ? "Peta tersimpan" : "Belum ada peta"} · {s.units.length} unit di database
            </p>
          </div>
        </div>
        <div className="flex gap-2 text-xs">
          <Stat id={STUDIO.statLots} label="Kavling di peta" value={st?.total_lots ?? 0} />
          <Stat id={STUDIO.statCoverage} label="Unit sudah di peta" value={`${st?.coverage_pct ?? 0}%`} tone={(st?.coverage_pct ?? 0) >= 100 ? "ok" : "warn"} />
          <Stat label="Kavling tanpa unit" value={s.unmappedLots.length} tone={s.unmappedLots.length ? "warn" : "ok"} />
        </div>
      </div>

      <StudioToolbar s={s} bgOpacity={bgOpacity} setBgOpacity={setBgOpacity} />

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[1fr_340px]">
        <div className="min-h-[420px]">
          {s.plan || s.tool === "draw" ? (
            <StudioCanvas plan={s.plan || { view_box: "0 0 1600 1000", shapes: [] }} unitsById={s.unitsById}
              selectedId={s.selectedId} tool={s.tool} bgOpacity={bgOpacity} colorMode={s.colorMode} palette={s.palette}
              onShapeClick={s.clickShape} onDrawDone={(pts) => s.addShape(pts, "lot")}
              onVertexMove={(sid, pts) => s.patchShape(sid, { points: pts }, { silent: true })} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed bg-muted/20 p-8 text-center">
              <MapPinned className="mb-3 h-10 w-10 text-muted-foreground" />
              <h2 className="text-base font-semibold md:text-lg">Mulai dari gambar site plan Anda</h2>
              <p className="mt-1 max-w-md text-sm text-muted-foreground">
                <strong>Unggah SVG</strong> dari arsitek — kotak kavling dan nomor di dalamnya dibaca otomatis lalu
                dicocokkan ke unit. Atau pasang <strong>gambar PNG/JPG atau PDF</strong> (halaman dirender otomatis) dan pilih
                alat <strong>Gambar kavling</strong> untuk menjiplak poligon di atasnya.
              </p>
            </div>
          )}
        </div>
        <aside data-testid={STUDIO.sidebar} className="min-h-0 overflow-y-auto rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="w-full">
              <TabsTrigger data-testid={STUDIO.tabShape} value="shape" className="flex-1">Bentuk</TabsTrigger>
              <TabsTrigger data-testid={STUDIO.tabUnits} value="units" className="flex-1">Unit ({s.unmappedUnits.length})</TabsTrigger>
              <TabsTrigger data-testid={STUDIO.tabCreate} value="create" className="flex-1">Buat unit ({s.unmappedLots.length})</TabsTrigger>
            </TabsList>
            <TabsContent value="shape" className="mt-3"><ShapePanel s={s} /></TabsContent>
            <TabsContent value="units" className="mt-3"><UnitsPanel s={s} /></TabsContent>
            <TabsContent value="create" className="mt-3"><CreateUnitsPanel s={s} /></TabsContent>
          </Tabs>
        </aside>
      </div>
    </div>
  );
}

function Stat({ id, label, value, tone }) {
  const cls = tone === "ok" ? "border-emerald-200 bg-emerald-50 text-emerald-800"
    : tone === "warn" ? "border-amber-200 bg-amber-50 text-amber-800" : "bg-card";
  return (
    <div data-testid={id} className={`rounded-lg border px-3 py-1.5 ${cls}`}>
      <div className="text-[10px] uppercase tracking-wide opacity-70">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
    </div>
  );
}
