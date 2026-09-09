import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Map as MapIcon, RefreshCw, Search, Maximize2, Minimize2, MapPinned, EyeOff, Eye, Share2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { LoadingKpis, ErrorState } from "@/components/patterns/StateViews";
import PlotMap from "@/components/siteplan/PlotMap";
import PlanLegend from "@/components/siteplan/PlanLegend";
import PlanModeLegend from "@/components/siteplan/PlanModeLegend";
import ShareShowroomDialog from "@/components/siteplan/ShareShowroomDialog";
import SvgPlanMap from "@/components/siteplan/SvgPlanMap";
import UnitQuickCard from "@/components/siteplan/UnitQuickCard";
import UnitDetailDrawer from "@/components/siteplan/UnitDetailDrawer";
import { makeScales, unitKey } from "@/components/siteplan/planStyles";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { SITE_PLAN } from "@/constants/testIds";


/**
 * Site Plan & Showroom Digital.
 *
 * Fase 28: peta berbasis SVG (kavling/jalan/taman/fasilitas) dengan 3 tingkat interaksi —
 * sorot (tooltip) → klik (kartu ringkas) → Detail Lengkap (drawer bertab), plus empat mode
 * warna infografis: siklus penjualan, progres pembangunan, heatmap harga, dan heatmap
 * lama tak terjual (Fase 28b). Halaman publik/marketing dibagikan lewat tombol Bagikan.
 * Bila proyek belum punya peta SVG, tata letak blok otomatis dipakai sebagai fallback.
 */
export default function SitePlanPage() {
  const { can } = useAuth();
  const navigate = useNavigate();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  // Menahan unit di Site Plan berjalan lewat `POST /deals/reserve`, yang dipaksakan dengan
  // `deals:create` — BUKAN `reservations:create`. Resource `reservations` ada di matriks RBAC
  // tetapi tidak dipaksakan endpoint mana pun, jadi memakainya di sini akan membuat tombol
  // bergantung pada izin yang tidak pernah dibaca server (gate `verify_rbac_ui` menangkapnya).
  const canReserve = can("deals", "create");
  const canSetup = can("projects", "update");
  const canShare = can("showroom", "update");

  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [term, setTerm] = useState("");
  const [mode, setMode] = useState("sales");
  const [highlight, setHighlight] = useState("");
  const [hover, setHover] = useState(null);
  const [pick, setPick] = useState(null);
  const [detail, setDetail] = useState(null);
  const [share, setShare] = useState(false);
  const [showroom, setShowroom] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [zoom, setZoom] = useState(1);
  const mapWrap = useRef(null);

  const loadProjects = useCallback(async () => {
    try {
      const res = await api.get("/projects");
      const rows = res.data?.data || [];
      setProjects(rows);
      setProjectId((prev) => prev || rows[0]?.id || "");
      if (!rows.length) setLoading(false);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar proyek.");
      setLoading(false);
    }
  }, []);

  const loadPlan = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const res = await api.get(`/site-plan/${projectId}`);
      setPlan(res.data?.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat site plan.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { loadProjects(); }, [loadProjects]);
  useEffect(() => { loadPlan(); }, [loadPlan]);

  const units = useMemo(() => plan?.units || [], [plan]);
  const svgPlan = plan?.plan || null;
  const unitsById = useMemo(
    () => Object.fromEntries(units.map((u) => [u.id, u])), [units]);
  // Skala heatmap dihitung SEKALI dari kavling proyek aktif, lalu dipakai bersama
  // peta, legenda, dan kartu ringkas agar warna & ambangnya tidak pernah berbeda.
  const scales = useMemo(() => makeScales(units), [units]);

  // Deep link ?unit=A-01 → langsung buka kartu kavling (untuk dibagikan ke pembeli).
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("unit");
    if (!code || !units.length) return;
    const u = units.find((x) => String(x.code).toLowerCase() === code.toLowerCase());
    if (u) setPick({ unit: u, rect: null });
  }, [units]);

  const isMatch = useCallback((u) => {
    if (status && u.status !== status) return false;
    if (type && u.type !== type) return false;
    if (highlight && unitKey(u, mode, scales) !== highlight) return false;
    if (term) {
      const q = term.toLowerCase();
      const hit = `${u.code} ${u.type || ""} ${privacy ? "" : u.buyer_name || ""}`.toLowerCase();
      if (!hit.includes(q)) return false;
    }
    return true;
  }, [status, type, term, highlight, mode, privacy, scales]);

  const visible = useMemo(() => units.filter(isMatch), [units, isMatch]);
  const stats = plan?.stats;

  const reserve = async (u) => {
    try {
      await api.post("/deals/reserve", { unit_id: u.id });
      toast.success(`Kavling ${u.code} berhasil direservasi.`);
      setPick(null);
      await loadPlan();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat reservasi.");
    }
  };

  const sanitize = (u) => (privacy ? { ...u, buyer_name: null } : u);

  if (loading) return <LoadingKpis count={5} />;
  if (error) return <ErrorState message={error} onRetry={loadPlan} />;

  return (
    <div data-testid={SITE_PLAN.page} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <MapIcon className="h-5 w-5 text-primary" />
          <div>
            <h1 className="page-title">Site Plan & Showroom Digital</h1>
            <p className="text-xs text-muted-foreground">
              Peta interaktif: sorot untuk ringkas, klik untuk kartu kavling, lalu buka detail lengkap.
              {svgPlan ? ` Peta ${svgPlan.source === "uploaded" ? "dari SVG arsitek" : "hasil generator"} · cakupan ${svgPlan.stats?.coverage_pct || 0}%.`
                : " Peta SVG belum disiapkan — sementara memakai tata letak blok otomatis."}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger data-testid={SITE_PLAN.projectSelect} className="w-60">
              <SelectValue placeholder="Pilih proyek" />
            </SelectTrigger>
            <SelectContent>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" data-testid={SITE_PLAN.privacyToggle}
            aria-label="Sembunyikan data sensitif" title="Mode publik: sembunyikan nama pembeli"
            onClick={() => setPrivacy((v) => !v)}>
            {privacy ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </Button>
          <Button variant="outline" size="icon" data-testid={SITE_PLAN.showroomBtn}
            aria-label="Mode showroom layar penuh" onClick={() => setShowroom((v) => !v)}>
            {showroom ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          {canShare ? (
            <Button variant="outline" data-testid={SITE_PLAN.shareBtn}
              onClick={() => setShare(true)}>
              <Share2 className="mr-1.5 h-4 w-4" /> Bagikan
            </Button>
          ) : null}
          {canSetup ? (
            <Button variant="outline" data-testid={SITE_PLAN.studioBtn}
              onClick={() => navigate(`/site-plan/studio/${projectId}`)}>
              <MapPinned className="mr-1.5 h-4 w-4" /> Studio Peta
            </Button>
          ) : null}
          <Button variant="outline" size="icon" data-testid={SITE_PLAN.refresh}
            aria-label="Muat ulang peta" onClick={loadPlan}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {!showroom ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <MetricCard label="Total kavling" value={stats?.total || 0} tone="primary" />
          <MetricCard label="Tersedia" value={stats?.counts?.available || 0} tone="emerald"
            hint={`${stats?.available_pct || 0}% dari total`} />
          <MetricCard label="Reserved / Booked"
            value={(stats?.counts?.reserved || 0) + (stats?.counts?.booked || 0)} tone="amber" />
          <MetricCard label="Absorpsi" value={`${stats?.absorption_pct || 0}%`} tone="indigo"
            hint="Booked + terjual / total" />
          <MetricCard label="Nilai tersedia" value={stats?.available_value || 0} tone="muted"
            format="idr" hint={`Total portofolio ${formatIDR(stats?.total_value)}`} />
        </div>
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-44 space-y-1">
            <span className="text-xs text-muted-foreground">Status</span>
            <ReferenceSelect group="unit_status" value={status} onChange={setStatus}
              allowEmpty emptyLabel="Semua status" testId={SITE_PLAN.statusFilter} />
          </div>
          <div className="w-44 space-y-1">
            <span className="text-xs text-muted-foreground">Tipe unit</span>
            <ReferenceSelect group="unit_type" value={type} onChange={setType}
              allowEmpty emptyLabel="Semua tipe" testId={SITE_PLAN.typeFilter} />
          </div>
          <div className="w-56 space-y-1">
            <span className="text-xs text-muted-foreground">Cari kavling / pembeli</span>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input data-testid={SITE_PLAN.search} value={term} className="pl-8"
                placeholder="mis. A-01" onChange={(e) => setTerm(e.target.value)} />
            </div>
          </div>
        </div>
        <p data-testid={SITE_PLAN.visibleCount} className="text-sm text-muted-foreground">
          Menampilkan <span className="font-semibold text-foreground">{visible.length}</span> dari {units.length} kavling
        </p>
      </div>

      <PlanModeLegend mode={mode} onMode={(m) => { setMode(m); setHighlight(""); }} units={units}
        highlight={highlight} onHighlight={setHighlight} scales={scales} />

      {!units.length ? (
        <EmptyState icon={MapIcon} title="Belum ada kavling di proyek ini"
          description="Buka Studio Peta: unggah SVG/gambar site plan dan lahirkan unit langsung dari kavling di peta."
          actionLabel={canSetup ? "Buka Studio Peta" : undefined}
          onAction={() => navigate(`/site-plan/studio/${projectId}`)} />
      ) : (
        <div ref={mapWrap} className="relative">
          {svgPlan ? (
            <SvgPlanMap viewBox={svgPlan.view_box} shapes={svgPlan.shapes} unitsById={unitsById}
              background={svgPlan.background}
              mode={mode} selectedId={pick?.unit?.id} isMatch={isMatch} fullscreen={showroom}
              scales={scales} onHover={setHover}
              onSelect={(p) => { setHover(null); setPick({ unit: sanitize(p.unit), rect: p.rect }); }} />
          ) : (
            <>
              <div className="mb-2 flex items-center gap-2">
                <Button size="sm" variant="outline" data-testid={SITE_PLAN.zoomOut}
                  aria-label="Perkecil" onClick={() => setZoom((z) => Math.max(0.5, z - 0.15))}>−</Button>
                <Button size="sm" variant="outline" data-testid={SITE_PLAN.zoomReset}
                  aria-label="Reset zoom" onClick={() => setZoom(1)}>Reset</Button>
                <Button size="sm" variant="outline" data-testid={SITE_PLAN.zoomIn}
                  aria-label="Perbesar" onClick={() => setZoom((z) => Math.min(2.5, z + 0.15))}>+</Button>
                <span className="text-xs text-muted-foreground">
                  Peta SVG belum disiapkan untuk proyek ini.
                </span>
              </div>
              <PlotMap canvas={plan?.canvas} blocks={plan?.blocks} units={units} zoom={zoom}
                selectedId={pick?.unit?.id} isMatch={isMatch}
                onSelect={(u) => setPick({ unit: sanitize(u), rect: null })} />
              <PlanLegend counts={stats?.counts} />
            </>
          )}

          {/* Tingkat 1 — tooltip sorot */}
          {hover?.unit && !pick ? (
            <div data-testid={SITE_PLAN.hoverCard}
              className="pointer-events-none absolute z-10 rounded-lg border bg-card px-2.5 py-1.5 text-xs shadow-lg"
              style={{
                left: Math.min(
                  Math.max(8, (hover.rect?.left || 0) - (mapWrap.current?.getBoundingClientRect().left || 0) + 12),
                  (mapWrap.current?.getBoundingClientRect().width || 400) - 220),
                top: Math.max(8, (hover.rect?.top || 0) - (mapWrap.current?.getBoundingClientRect().top || 0) - 44),
              }}>
              <p className="font-semibold">{hover.unit.code} · {hover.unit.type || "-"}</p>
              <p className="text-muted-foreground">
                {hover.unit.luas_bangunan ? `${hover.unit.luas_bangunan}/${hover.unit.luas_tanah || 0} m² · ` : ""}
                {formatIDR(hover.unit.price)}
              </p>
              <p className="text-muted-foreground">
                Progres {Number(hover.unit.construction_progress || 0)}% · klik untuk detail
              </p>
            </div>
          ) : null}

          {/* Tingkat 2 — kartu ringkas mengembang */}
          <UnitQuickCard pick={pick} mode={mode} canReserve={canReserve} scales={scales}
            containerRect={mapWrap.current?.getBoundingClientRect()}
            onClose={() => setPick(null)}
            onDetail={(u) => { setDetail(u); }}
            onReserve={reserve} />
        </div>
      )}

      {/* Tingkat 3 — drawer detail lengkap */}
      {detail ? (
        <UnitDetailDrawer projectId={projectId} unit={detail} canSeePrivate={!privacy}
          onClose={() => setDetail(null)} />
      ) : null}

      <ShareShowroomDialog open={share} onOpenChange={setShare} projectId={projectId}
        projectName={projects.find((p) => p.id === projectId)?.name} />
    </div>
  );
}
