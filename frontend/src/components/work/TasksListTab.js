import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle, CalendarClock, CheckCircle2, Clock, Hourglass, Inbox, ShieldAlert,
} from "lucide-react";

import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import AgingCell from "@/components/patterns/AgingCell";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import { dueLabel, fromNow } from "@/utils/formatters";
import { downloadCsv } from "@/utils/tableCsv";
import { slaFilter } from "@/utils/agingFilter";
import api from "@/services/apiClient";
import { cn } from "@/lib/utils";
import { WORK, DT } from "@/constants/testIds";

/**
 * TasksListTab — daftar tugas sebagai TABEL PRO (US-40-1 & US-40-4).
 *
 * Kenapa berubah dari kartu “Task Inbox”:
 *   * kartu ember (Terlambat/Hari ini/…) bagus untuk 10 tugas, tetapi supervisor dengan 200
 *     tugas tidak bisa mencari, memfilter per tipe/prioritas, mengurutkan per tenggat, atau
 *     mengekspor — semuanya sekarang ada dan dikerjakan SERVER (jujur pada seluruh hasil);
 *   * ember tetap ada sebagai chip filter yang angkanya dihitung database, sehingga KPI
 *     Beranda bisa menaut ke ember yang persis sama (`?bucket=overdue`);
 *   * pandangan kartu tidak hilang — Beranda tetap memakai Task Inbox untuk “Hari Saya”.
 */
const BUCKETS = [
  { key: "", label: "Semua", icon: Inbox },
  { key: "overdue", label: "Terlambat", icon: AlertTriangle, count: "overdue" },
  { key: "today", label: "Hari ini", icon: Clock, count: "today" },
  { key: "upcoming", label: "Akan datang", icon: CalendarClock, count: "upcoming" },
  { key: "waiting", label: "Ditunda", icon: Hourglass, count: "waiting" },
  { key: "review", label: "Perlu verifikasi", icon: CheckCircle2, count: "review" },
];

export default function TasksListTab({ scopes = [], onOpenTask, onChanged }) {
  const { options, labelOf } = useReference();
  const { query, setQuery, reset, apiParams } = useListQuery({
    filters: {
      scope: "mine", bucket: "", type: [], priority: [], status: [], sla: "", unassigned: "",
    },
    sort: "due_date", direction: "asc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/work/tasks", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat tugas.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const counts = data?.counts || {};
  const scope = query.scope || "mine";
  // “PIC” hanya bermakna di luar scope `mine` (semua barisnya milik saya sendiri).
  const showPic = scope !== "mine";

  const columns = useMemo(() => [
    {
      key: "title", header: "Tugas", sortable: true, width: "30%",
      render: (t) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{t.title}</p>
          <p className="truncate text-xs text-muted-foreground">
            {labelOf("task_type", t.type)}
            {t.related_entity_type ? ` · ${t.related_entity_type}` : ""}
            {t.jobdesk_code ? ` · ${t.jobdesk_code}` : ""}
          </p>
        </div>
      ),
      exportValue: (t) => t.title,
    },
    {
      key: "priority", header: "Prioritas", sortable: true,
      render: (t) => <StatusPill status={t.priority} group="priority" />,
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (t) => (
        <div className="flex flex-wrap items-center gap-1">
          <StatusPill status={t.status} group="task_status" />
          {t.sla_breached ? (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-700">
              <ShieldAlert className="h-3 w-3" /> SLA
            </span>
          ) : null}
        </div>
      ),
      exportValue: (t) => `${t.status}${t.sla_breached ? " (SLA terlampaui)" : ""}`,
    },
    {
      key: "assigned_to", header: "PIC", sortable: true, hidden: !showPic,
      render: (t) => (
        <span className="text-sm">
          {t.assigned_to || <span className="text-amber-700">belum bertuan</span>}
        </span>
      ),
      exportValue: (t) => t.assigned_to || "belum bertuan",
    },
    {
      key: "division", header: "Divisi", sortable: true, hidden: true,
      render: (t) => <span className="text-sm">{labelOf("division", t.division) || "-"}</span>,
    },
    {
      key: "due_date", header: "Jatuh tempo", sortable: true,
      render: (t) => {
        const d = dueLabel(t.due_date);
        const late = t.due_date && t.due_date < new Date().toISOString()
          && !["done", "completed", "cancelled"].includes(t.status);
        return (
          <span className={cn("text-sm", late ? "font-medium text-rose-700" : "")}>
            {t.due_date ? d.text : "tanpa tenggat"}
          </span>
        );
      },
      exportValue: (t) => t.due_date || "",
    },
    {
      key: "age_hours", header: "Umur (total · status)",
      render: (t) => <AgingCell ageHours={t.age_hours} stageAgeHours={t.stage_age_hours}
        slaHours={t.stage_sla_hours} state={t.sla_state} />,
      exportValue: (t) => `${Math.round(t.age_hours || 0)}j`,
    },
    {
      key: "created_at", header: "Dibuat", sortable: true, hidden: true,
      render: (t) => <span className="text-xs text-muted-foreground">{fromNow(t.created_at)}</span>,
    },
  ], [labelOf, showPic]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "type", label: "Tipe", type: "multiselect", options: options("task_type") },
      { key: "priority", label: "Prioritas", type: "multiselect", options: options("priority") },
      { key: "status", label: "Status", type: "multiselect", options: options("task_status") },
      slaFilter(options("sla_state"),
        [{ value: "breached", label: "Tenggat tugas terlampaui" }]),
      ...(showPic ? [{ key: "unassigned", label: "Kepemilikan", type: "select",
        options: [{ value: "1", label: "Belum bertuan" }] }] : []),
    ]} />
  );

  const runBulk = async (rows, clear, fn, okMsg) => {
    setBusy(true);
    const res = await Promise.allSettled(rows.map(fn));
    const ok = res.filter((r) => r.status === "fulfilled").length;
    const bad = res.length - ok;
    if (ok) toast.success(`${ok} ${okMsg}`);
    if (bad) toast.error(`${bad} tugas gagal diproses (cek izin/status tugas).`);
    setBusy(false);
    clear?.();
    load();
    onChanged?.();
  };

  const bulkActions = [
    {
      key: "complete", label: "Tandai selesai", testId: WORK.bulkComplete,
      onRun: (rows, clear) => runBulk(rows, clear,
        (t) => api.post(`/work/tasks/${t.id}/complete`, { outcome: "Selesai (aksi massal)" }),
        "tugas ditandai selesai."),
    },
    {
      key: "snooze", label: "Tunda 1 hari", testId: WORK.bulkSnooze,
      onRun: (rows, clear) => runBulk(rows, clear,
        (t) => api.post(`/work/tasks/${t.id}/snooze`,
          { until: new Date(Date.now() + 86400000).toISOString() }),
        "tugas ditunda 1 hari."),
    },
    {
      key: "export", label: "Ekspor terpilih", testId: WORK.bulkExport,
      onRun: (rows) => {
        downloadCsv(columns, rows, "tugas-terpilih");
        toast.success(`${rows.length} baris diekspor ke CSV.`);
      },
    },
  ];

  const hasNarrow = !!(query.q || query.bucket || query.sla || query.unassigned
    || (query.type || []).length || (query.priority || []).length || (query.status || []).length);

  return (
    <div className="space-y-3">
      {scopes.length > 1 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Cakupan
          </span>
          {scopes.map((s) => (
            <button key={s.id} type="button" data-testid={`${WORK.scopePrefix}-${s.id}`}
              data-active={scope === s.id ? "true" : "false"}
              onClick={() => setQuery({ scope: s.id, unassigned: "" })}
              className={cn("rounded-lg border px-3 py-1 text-sm font-medium transition-colors",
                scope === s.id ? "border-primary bg-primary/10 text-primary"
                  : "bg-card text-muted-foreground hover:bg-secondary")}>
              {s.label}
            </button>
          ))}
        </div>
      ) : (
        <span data-testid={`${WORK.scopePrefix}-mine`}
          className="inline-block rounded-lg border bg-card px-3 py-1 text-sm text-muted-foreground shadow-[var(--shadow-card)]">
          Tugas yang ditugaskan kepada saya
        </span>
      )}

      {/* Chip ember = filter server-side. Angkanya dihitung database atas SELURUH cakupan,
          bukan atas baris yang sedang terlihat, sehingga bisa dipertanggungjawabkan. */}
      <div className="flex flex-wrap gap-2">
        {BUCKETS.map((b) => {
          const on = (query.bucket || "") === b.key;
          const Icon = b.icon;
          return (
            <button key={b.key || "all"} type="button"
              data-testid={`${WORK.bucketPrefix}-${b.key || "all"}`}
              data-active={on ? "true" : "false"}
              onClick={() => setQuery({ bucket: b.key, status: [] })}
              className={cn("inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm",
                "transition-colors",
                on ? "border-primary bg-primary/10 text-primary"
                  : "bg-card hover:bg-secondary")}>
              <Icon className="h-3.5 w-3.5" /> {b.label}
              {b.count ? (
                <span className="tabular-nums text-xs text-muted-foreground">
                  {counts[b.count] ?? 0}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <DataTable testId={WORK.taskTable}
        testIds={{ row: WORK.taskRow, search: WORK.taskSearch, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading || busy} error={error}
        filters={filters} bulkActions={bulkActions} label="tugas" exportName="tugas"
        onRefresh={load} searchPlaceholder="Cari judul / keterangan / hasil kerja…"
        onRowClick={(t) => onOpenTask?.(t.id)}
        emptyTitle={hasNarrow ? "Tidak ada tugas yang cocok" : "Tidak ada tugas aktif"}
        emptyDescription={hasNarrow
          ? "Longgarkan filter atau pilih ember “Semua”."
          : "Semua pekerjaan pada cakupan ini sudah tuntas. Tugas baru muncul otomatis dari mesin jobdesk."}
        emptyActionLabel={hasNarrow ? "Reset filter" : ""}
        emptyAction={hasNarrow ? () => reset() : null} />
    </div>
  );
}
