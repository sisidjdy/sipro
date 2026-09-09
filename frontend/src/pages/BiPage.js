import React, { useEffect, useMemo, useState } from "react";
import { BarChart3, Boxes, LineChart, Megaphone, Users2, BookOpen, Info } from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import EmptyState from "@/components/patterns/EmptyState";
import FilterBar from "@/components/patterns/FilterBar";
import { LoadingCards } from "@/components/patterns/StateViews";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import MetricDictionaryTab from "@/components/bi/MetricDictionaryTab";
import {
  ExecutiveDashboard, MarketingDashboard, ProjectCostDashboard, SalesLeadDashboard, TeamDashboard,
} from "@/components/bi/dashboards";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { BI } from "@/constants/testIds";

/**
 * BiPage (`/bi`) — hub **Analitik & BI** (Fase 44, acuan `docs/v2/31_ANALYTICS_BI_SPEC.md`).
 *
 * Menu ini terakhir yang berstatus “Segera Hadir”. Sebelumnya setiap pertanyaan manajemen
 * dijawab dengan mengekspor tabel lalu menghitung di spreadsheet pribadi — dan setiap orang
 * membawa angka yang sedikit berbeda ke rapat. Sekarang: lima dashboard persona, satu kamus
 * metrik, dan satu aturan yang tidak bisa dilanggar layar — angka yang datanya belum ada
 * ditulis “belum ada data”, bukan 0.
 *
 * Filter berlaku LINTAS tab: rentang cepat (7/30/90 hari…), tanggal kustom (menang atas
 * rentang cepat — aturan `resolve_range` server), dan proyek. Filter proyek hanya dihormati
 * dashboard yang datanya memang per-proyek (Eksekutif, Penjualan, Proyek & Biaya) — untuk
 * Marketing & Tim ditampilkan keterangan, bukan diam-diam diabaikan.
 */
export default function BiPage() {
  const { can, permsKnown } = useAuth();
  const { labelOf } = useReference();
  const canView = can("analytics", "view");
  const [period, setPeriod] = useState("30d");
  const [filters, setFilters] = useState({ project: "", date_from: "", date_to: "" });
  const [projects, setProjects] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/projects").then((res) => {
      const rows = Array.isArray(res.data.data) ? res.data.data : [];
      setProjects(rows.map((p) => ({ value: p.id, label: p.name })));
      setError("");
    }).catch((e) => {
      setProjects([]);
      setError(e?.response?.data?.detail || "Daftar proyek untuk filter gagal dimuat.");
    });
  }, []);

  const baseParams = useMemo(() => {
    const p = { period };
    if (filters.date_from && filters.date_to) {
      p.date_from = filters.date_from; p.date_to = filters.date_to;
    }
    return p;
  }, [period, filters.date_from, filters.date_to]);
  const projectParams = useMemo(() => (filters.project
    ? { ...baseParams, project_id: filters.project } : baseParams), [baseParams, filters.project]);
  const projectName = projects.find((p) => p.value === filters.project)?.label;

  const header = (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Analitik & BI</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Lima dashboard untuk lima pertanyaan yang berbeda, semuanya dihitung dari data
            operasional yang sama — bukan hitungan kedua. Setiap angka membawa
            <strong> status kelengkapan</strong>, <strong>rumusnya</strong>, dan
            <strong> tautan ke daftar barisnya</strong>.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-44">
          <ReferenceSelect group="analytics_period" value={period} onChange={setPeriod}
            testId={BI.period} placeholder="Rentang…" />
        </div>
        <FilterBar testId={BI.filterBar}
          filters={[
            { key: "project", label: "Proyek", type: "select", options: projects },
            { key: "tanggal", label: "Tanggal kustom", type: "daterange",
              fromKey: "date_from", toKey: "date_to" },
          ]}
          value={filters}
          onChange={(patch) => setFilters((cur) => ({ ...cur, ...patch }))}
          onReset={() => setFilters({ project: "", date_from: "", date_to: "" })} />
      </div>
      {error ? (
        <p data-testid={BI.projectsError} className="text-xs text-destructive">{error}</p>
      ) : null}
      {filters.date_from && !filters.date_to ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          Isi juga “Sampai tanggal” — rentang kustom baru dipakai bila keduanya terisi.
        </p>
      ) : null}
      {filters.project ? (
        <p data-testid={BI.projectHint}
          className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Info className="h-3.5 w-3.5 shrink-0" />
          Filter proyek <strong>{projectName}</strong> berlaku di dashboard Eksekutif,
          Penjualan & Proyek — Marketing dan Tim datanya tidak per-proyek.
        </p>
      ) : null}
    </div>
  );

  if (!canView) {
    return (
      <div data-testid={BI.page} className="space-y-4">
        {header}
        {/* Kalimat "tidak punya akses" hanya boleh muncul bila izinnya BENAR-BENAR sudah
            diketahui. Dulu profil sesi tanpa `permissions` (cacat jawaban `/auth/login`)
            membuat halaman ini menuduh hak akses — bahkan kepada super admin. */}
        {permsKnown ? (
          <EmptyState icon={BarChart3} title="Anda tidak punya akses ke Analitik & BI"
            description="Peran Anda tidak diberi izin melihat metrik. Hubungi admin bila memang
              perlu — halaman ini sengaja tidak menampilkan tabel kosong yang seolah-olah
              datanya tidak ada." />
        ) : (
          <LoadingCards count={4} />
        )}
      </div>
    );
  }

  return (
    <div data-testid={BI.page} className="space-y-4">
      {/* Nama tab = label SSOT `metric_persona`, BUKAN teks yang diketik ulang di sini:
          nama dashboard juga dipakai kamus metrik & jawaban API, jadi menuliskannya dua kali
          membuat "Kinerja Tim" di tab bisa berbeda dengan "Kinerja Tim" di kamus. */}
      <TabPage paramKey="hub" testId={BI.hubTab} header={header} tabs={[
        { key: "eksekutif", label: labelOf("metric_persona", "eksekutif"), icon: LineChart,
          content: <ExecutiveDashboard params={projectParams} /> },
        { key: "penjualan", label: labelOf("metric_persona", "penjualan"), icon: Users2,
          content: <SalesLeadDashboard params={projectParams} /> },
        { key: "marketing", label: labelOf("metric_persona", "marketing"), icon: Megaphone,
          content: <MarketingDashboard params={baseParams} /> },
        { key: "proyek", label: labelOf("metric_persona", "proyek"), icon: Boxes,
          content: <ProjectCostDashboard params={projectParams} /> },
        { key: "tim", label: labelOf("metric_persona", "tim"), icon: BarChart3,
          content: <TeamDashboard params={baseParams} /> },
        { key: "kamus", label: "Kamus Metrik", icon: BookOpen,
          content: <MetricDictionaryTab /> },
      ]} />
    </div>
  );
}
