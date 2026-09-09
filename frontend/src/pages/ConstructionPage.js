import React, { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ShieldCheck,
  ClipboardCheck, FileBarChart2, FileStack, HardHat, ListChecks, Smartphone, Waypoints,
} from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import EmptyState from "@/components/patterns/EmptyState";
import { AccessDenied, ErrorState } from "@/components/patterns/StateViews";
import BuildMonitorPanel from "@/components/construction/BuildMonitorPanel";
import BuildQueuePanel from "@/components/construction/BuildQueuePanel";
import BuildTemplatePanel from "@/components/construction/BuildTemplatePanel";
import DelayAnalyticsPanel from "@/components/construction/DelayAnalyticsPanel";
import ForemanBoard from "@/components/construction/ForemanBoard";
import InspectionsPanel from "@/components/construction/InspectionsPanel";
import ProjectPhasesPanel from "@/components/construction/ProjectPhasesPanel";
import ProjectSelect from "@/components/construction/ProjectSelect";
import WeeklyReportPanel from "@/components/construction/WeeklyReportPanel";
import WarrantyBoardPanel from "@/components/handover/WarrantyBoardPanel";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { selfPath } from "@/utils/hubNav";
import { BUILD, CONSTRUCTION, P50 } from "@/constants/testIds";

/**
 * PROGRES & MUTU KONSTRUKSI.
 *
 * Sebelum Fase 31 halaman ini hanya berisi kotak persen yang diketik manual pada fase
 * PROYEK, lalu angka itu ditimpa ke SEMUA unit — jadi tiap rumah tampak punya progres
 * sama dan tidak ada tenggat, bukti, maupun eskalasi.
 *
 * Sekarang dipisah jujur sesuai objeknya:
 *   1. Papan Mandor         — "kerja hari ini" per orang (Fase 32, ramah dipakai dari HP)
 *   2. Monitoring Unit      — jadwal berbukti per rumah (progres = pekerjaan terverifikasi)
 *   3. Antrean Kerja        — pekerjaan saya / menunggu verifikasi, lintas unit
 *   4. Infrastruktur Kawasan— pekerjaan milik proyek (jalan, drainase, gerbang)
 *   5. QC & Inspeksi        — inspeksi formal + punch list
 *   6. Laporan & Analitik   — laporan mingguan direksi + analitik keterlambatan (Fase 32)
 *   7. Template Jadwal      — tahapan per tipe unit yang bisa dikonfigurasi
 */
// PENGECUALIAN SAH dari aturan "jangan salin matriks RBAC": ini BUKAN gerbang izin —
// semua peran di bawah boleh membuka kedua tab. Yang dipilih di sini hanya TAB BAWAAN
// sesuai cara kerja peran: pelaksana lapangan memulai dari Papan Mandor, yang lain dari
// Monitoring. Memakai izin (`construction:update`) justru SALAH karena akan ikut
// mengubah tab bawaan Manajer Proyek. Dijaga daftar izin di `verify_rbac_ui.py`.
const FIELD_ROLES = ["site_engineer"];

export default function ConstructionPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const params = new URLSearchParams(loc.search);
  const [projectId, setProjectId] = useState(null);
  // Pelaksana lapangan membuka halaman ini untuk BEKERJA, bukan memantau → Papan Mandor
  // menjadi tab awal mereka. Deep link (?tab=) selalu menang.
  const [tab, setTab] = useState(params.get("tab")
    || (FIELD_ROLES.includes(user?.nav_role || user?.role) ? "board" : "monitor"));
  const [focusItem, setFocusItem] = useState(params.get("item") || null);
  const [phases, setPhases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const focusReport = params.get("report") || null;

  // Panggilan ini sekaligus menjadi PEMERIKSA HAK AKSES halaman: bila 403, seluruh
  // halaman diganti satu penjelasan sopan alih-alih setiap panel memunculkan pesan
  // teknis backend berulang kali.
  const loadPhases = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const r = await api.get(`/construction/project/${projectId}/phases`);
      setPhases(r.data.data || []);
      setDenied(false);
    } catch (e) {
      if (e?.response?.status === 403) {
        setDenied(true);
      } else {
        setError(e?.response?.data?.detail || "Gagal memuat pekerjaan kawasan proyek.");
      }
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { loadPhases(); }, [loadPhases]);

  const changeTab = (v) => {
    setTab(v);
    // URL mengikuti tab supaya tautan bisa dibagikan & tombol kembali bekerja wajar.
    // Pathname-nya adalah pathname SEKARANG: halaman ini juga dipakai sebagai tab di hub
    // `/build`, dan menulis "/construction" di sana akan menendang pemakai keluar hub.
    const q = new URLSearchParams(loc.search);
    q.set("tab", v);
    q.delete("item");
    nav({ pathname: selfPath(loc.pathname, "/construction"), search: `?${q.toString()}` },
      { replace: true });
  };

  return (
    <div data-testid={CONSTRUCTION.page} className="space-y-4">
      <div className="sticky top-0 z-20 -mx-4 border-b bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <HardHat className="h-5 w-5 text-primary" />
            <div>
              <h1 className="page-title">Progres & Mutu Konstruksi</h1>
              <p className="text-xs text-muted-foreground">
                Setiap tahap pekerjaan menjadi tugas berinstruksi dengan bukti foto dan
                verifikasi supervisor — progres rumah dihitung dari situ.
              </p>
            </div>
          </div>
          <ProjectSelect value={projectId} onChange={setProjectId}
            testId={CONSTRUCTION.projectSelect} />
        </div>
      </div>

      {!projectId ? (
        <EmptyState icon={HardHat} title="Pilih proyek"
          description="Pilih proyek untuk memantau jadwal pembangunan tiap rumah, antrean kerja, dan mutu pekerjaan." />
      ) : denied ? (
        <AccessDenied testId={CONSTRUCTION.denied}
          title="Progres & Mutu Konstruksi hanya untuk tim Proyek"
          description="Halaman ini memuat jadwal pembangunan, bukti kerja, dan mutu tiap rumah — dibuka untuk Manajer Proyek, pelaksana lapangan, Keuangan, dan Direksi."
          askWho="Bila Anda memang perlu memantau progres rumah pembeli, mintakan hak akses ke admin sistem." />
      ) : (
        <Tabs value={tab} onValueChange={changeTab} className="space-y-4">
          <TabsList className="flex h-auto flex-wrap justify-start">
            <TabsTrigger data-testid={BUILD.tabBoard} value="board">
              <Smartphone className="mr-1.5 h-3.5 w-3.5" /> Papan Mandor
            </TabsTrigger>
            <TabsTrigger data-testid={BUILD.tabMonitor} value="monitor">
              <HardHat className="mr-1.5 h-3.5 w-3.5" /> Monitoring Unit
            </TabsTrigger>
            <TabsTrigger data-testid={BUILD.tabQueue} value="queue">
              <ListChecks className="mr-1.5 h-3.5 w-3.5" /> Antrean Kerja
            </TabsTrigger>
            <TabsTrigger data-testid={BUILD.tabPhases} value="phases">
              <Waypoints className="mr-1.5 h-3.5 w-3.5" /> Infrastruktur Kawasan
            </TabsTrigger>
            <TabsTrigger data-testid={BUILD.tabQc} value="qc">
              <ClipboardCheck className="mr-1.5 h-3.5 w-3.5" /> QC & Inspeksi
            </TabsTrigger>
            <TabsTrigger data-testid={BUILD.tabReports} value="reports">
              <FileBarChart2 className="mr-1.5 h-3.5 w-3.5" /> Laporan & Analitik
            </TabsTrigger>
            <TabsTrigger data-testid={BUILD.tabTemplates} value="templates">
              <FileStack className="mr-1.5 h-3.5 w-3.5" /> Template Jadwal
            </TabsTrigger>
            {/* Fase 50A: pekerjaan garansi dikerjakan orang yang sama dengan pekerjaan
                pembangunan, jadi papannya menjadi TAB di sini (tanpa pintu sidebar baru). */}
            <TabsTrigger data-testid={P50.boardTab} value="warranty">
              <ShieldCheck className="mr-1.5 h-3.5 w-3.5" /> Garansi & Klaim
            </TabsTrigger>
          </TabsList>

          <TabsContent value="warranty">
            <WarrantyBoardPanel projectId={projectId} />
          </TabsContent>

          <TabsContent value="board">
            <ForemanBoard projectId={projectId} focusItemId={focusItem}
              onFocusHandled={() => setFocusItem(null)} />
          </TabsContent>

          <TabsContent value="monitor">
            <BuildMonitorPanel projectId={projectId} />
          </TabsContent>

          <TabsContent value="queue">
            <BuildQueuePanel projectId={projectId} />
          </TabsContent>

          <TabsContent value="phases">
            <ProjectPhasesPanel projectId={projectId} onChanged={loadPhases} />
          </TabsContent>

          <TabsContent value="qc" className="space-y-3">
            {error ? <ErrorState message={error} onRetry={loadPhases} /> : null}
            {loading ? (
              <p className="text-sm text-muted-foreground">Memuat daftar pekerjaan kawasan…</p>
            ) : null}
            {!loading && !phases.length ? (
              <p className="rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground">
                Belum ada pekerjaan kawasan pada proyek ini — inspeksi tetap bisa dibuat
                tanpa dikaitkan ke fase kawasan.
              </p>
            ) : null}
            <InspectionsPanel projectId={projectId} phases={phases} />
          </TabsContent>

          <TabsContent value="reports" className="space-y-5">
            <WeeklyReportPanel projectId={projectId} focusReportId={focusReport} />
            <DelayAnalyticsPanel projectId={projectId}
              onOpenTemplates={() => changeTab("templates")} />
          </TabsContent>

          <TabsContent value="templates">
            <BuildTemplatePanel projectId={projectId} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
