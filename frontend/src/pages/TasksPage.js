import React, { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Columns3, LayoutDashboard, LineChart, ListChecks, RefreshCw, Timer } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import TabPage from "@/components/patterns/TabPage";
import TasksListTab from "@/components/work/TasksListTab";
import TaskDetailSheet from "@/components/work/TaskDetailSheet";
import DivisionBoard from "@/components/work/DivisionBoard";
import JobdeskPanel from "@/components/work/JobdeskPanel";
import KanbanBoard from "@/components/work/KanbanBoard";
import DivisionReport from "@/components/work/DivisionReport";
import AgingReportTab from "@/components/work/AgingReportTab";
import CreateTaskDialog from "@/components/work/CreateTaskDialog";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import EmptyState from "@/components/patterns/EmptyState";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";

/**
 * TasksPage (`/tasks`) — hub **Kerja**: tugas (tabel pro), papan kanban, papan divisi,
 * rapor mingguan, dan katalog jobdesk.
 *
 * Fase 40d: tab SINKRON KE URL (`?tab=`) supaya KPI Beranda bisa menaut langsung ke tab
 * tugas dengan ember/filter tertentu (mis. `/tasks?tab=tasks&scope=all&bucket=overdue`) dan
 * tautannya bisa dibagikan. Daftar tugas dipindahkan ke `TasksListTab` (tabel pro dengan
 * cari/filter/sort/kolom/ekspor/aksi massal) — pandangan kartu ember tetap dipakai Beranda.
 */
export default function TasksPage() {
  const [meta, setMeta] = useState(null);      // { my_division, my_level, divisions }
  const [division, setDivision] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openTask, setOpenTask] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const loadMeta = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/work/divisions");
      setMeta({ ...res.data, divisions: res.data.data || [] });
      setDivision(res.data.my_division || (res.data.data || [])[0]?.code || "");
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data divisi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadMeta(); }, [loadMeta]);

  const isSupervisor = meta?.my_level === "supervisor" || meta?.my_level === "owner";
  const isOwner = meta?.my_level === "owner";

  const scopes = useMemo(() => {
    const list = [{ id: "mine", label: "Tugas Saya" }];
    if (isSupervisor) list.push({ id: "division", label: "Divisi Saya" });
    if (isOwner) list.push({ id: "all", label: "Semua Divisi" });
    return list;
  }, [isSupervisor, isOwner]);

  const activeDivision = isOwner ? division : meta?.my_division;

  const tabs = useMemo(() => [
    { key: "tasks", label: "Tugas", icon: ListChecks,
      content: <TasksListTab key={reloadKey} scopes={scopes}
        onOpenTask={(id) => setOpenTask(id)} /> },
    { key: "kanban", label: "Papan Kanban", icon: Columns3,
      content: <KanbanBoard division={activeDivision} onOpenTask={(t) => setOpenTask(t.id)} /> },
    // Fase 41 — pertanyaan yang dulu tidak bisa dijawab aplikasi: "mana yang menganggur
    // paling lama di tahapnya?". Ditempatkan di hub Kerja karena itu pertanyaan HARIAN,
    // bukan laporan bulanan.
    { key: "aging", label: "Umur Tahap & SLA", icon: Timer, content: <AgingReportTab /> },
    ...(isSupervisor ? [
      { key: "board", label: "Papan Divisi", icon: LayoutDashboard,
        content: <DivisionBoard division={division} onOpenTask={(t) => setOpenTask(t.id)} /> },
      { key: "report", label: "Rapor Mingguan", icon: LineChart,
        content: <DivisionReport division={activeDivision}
          onOpenTask={(t) => setOpenTask(t.id)} /> },
      { key: "jobdesk", label: "Katalog Jobdesk", icon: BookOpen,
        content: <JobdeskPanel division={activeDivision} canManage={isSupervisor}
          onChanged={() => setReloadKey((k) => k + 1)} /> },
    ] : []),
  ], [scopes, activeDivision, division, isSupervisor, reloadKey]);

  return (
    <div data-testid={WORK.tasksPage} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">
            Tugas &amp; Papan Divisi
          </h1>
          <p className="page-desc">
            Satu pintu pekerjaan: apa yang harus dikerjakan, siapa PIC-nya, dan mana yang
            sudah lewat SLA.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isOwner && (meta?.divisions || []).length ? (
            <Select value={division} onValueChange={setDivision}>
              <SelectTrigger data-testid={WORK.divisionSelect} className="w-52"
                aria-label="Pilih divisi untuk papan & rapor">
                <SelectValue placeholder="Pilih divisi" />
              </SelectTrigger>
              <SelectContent>
                {(meta?.divisions || []).map((d) => (
                  <SelectItem key={d.code} value={d.code}>{d.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          {isSupervisor ? (
            <CreateTaskDialog division={division}
              onDone={() => setReloadKey((k) => k + 1)} />
          ) : null}
          <Button size="sm" variant="outline" aria-label="Muat ulang"
            onClick={() => { loadMeta(); setReloadKey((k) => k + 1); }}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {error ? <ErrorState message={error} onRetry={loadMeta} /> : null}

      {/* Cakupan (mine/division/all) & daftar tab bergantung pada LEVEL pemakai, jadi tab
          baru ditampilkan setelah data divisi tiba — kalau tidak, chip cakupan sempat
          tampil salah lalu berubah sendiri (terlihat seperti bug). */}
      {loading && !meta ? <LoadingCards count={3} /> : null}
      {!loading && !error && !meta ? (
        <EmptyState icon={ListChecks} title="Data divisi belum tersedia"
          description="Belum ada divisi yang bisa dibaca akun Anda, jadi papan divisi & katalog jobdesk disembunyikan. Tugas pribadi tetap bisa dibuka setelah admin menempatkan Anda pada satu divisi."
          actionLabel="Muat ulang" onAction={loadMeta} />
      ) : null}
      {meta ? <TabPage tabs={tabs} /> : null}

      <TaskDetailSheet taskId={openTask} open={!!openTask}
        onOpenChange={(v) => !v && setOpenTask(null)}
        onChanged={() => setReloadKey((k) => k + 1)} />
    </div>
  );
}
