import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";

import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import AgingCell from "@/components/patterns/AgingCell";
import ComplaintDetailSheet from "@/components/complaints/ComplaintDetailSheet";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import { dueLabel, fromNow } from "@/utils/formatters";
import { downloadCsv } from "@/utils/tableCsv";
import { slaFilter } from "@/utils/agingFilter";
import api from "@/services/apiClient";
import { COMPLAINTS, DT } from "@/constants/testIds";

/**
 * ComplaintsListTab — daftar komplain sebagai tabel pro (US-40-1).
 *
 * Dulu: pencarian + satu dropdown status, tanpa sort, tanpa ekspor, tanpa kolom umur, dan
 * SLA hanya muncul sebagai teks. Akibatnya CS tidak bisa menjawab pertanyaan paling sering
 * ditanya manajemen: “mana komplain konstruksi prioritas tinggi yang paling lama menganggur?”
 * Sekarang: filter multi (status/prioritas/kategori/SLA/tanggal), sort server-side, kolom
 * umur (total & umur status), ekspor CSV sesuai filter aktif.
 */
export default function ComplaintsListTab({ onChanged }) {
  const { labelOf, options } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: {
      status: [], priority: [], category: [], sla: "", created_from: "", created_to: "",
    },
    sort: "created_at", direction: "desc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/complaints", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat komplain.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const columns = useMemo(() => [
    {
      key: "subject", header: "Subjek", sortable: true, width: "28%",
      render: (c) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{c.subject}</p>
          <p className="text-xs text-muted-foreground">
            {labelOf("complaint_category", c.category)}
          </p>
        </div>
      ),
      exportValue: (c) => c.subject,
    },
    {
      key: "customer_name", header: "Pelanggan / Unit", sortable: true,
      render: (c) => (
        <div className="min-w-0">
          <p className="truncate text-sm">{c.customer_name || "-"}</p>
          <p className="text-xs text-muted-foreground">{c.unit_code || "-"}</p>
        </div>
      ),
      exportValue: (c) => `${c.customer_name || "-"} (${c.unit_code || "-"})`,
    },
    {
      key: "priority", header: "Prioritas", sortable: true,
      render: (c) => <StatusPill status={c.priority} group="priority" />,
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (c) => <StatusPill status={c.status} group="complaint_status" />,
    },
    {
      key: "sla_due_at", header: "SLA", sortable: true,
      render: (c) => {
        if (["resolved", "closed"].includes(c.status)) {
          return <span className="text-xs text-muted-foreground">selesai</span>;
        }
        if (c.sla_breached) {
          return (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-700">
              <AlertTriangle className="h-3.5 w-3.5" /> Lewat SLA
            </span>
          );
        }
        return <span className="text-xs text-muted-foreground">{dueLabel(c.sla_due_at).text}</span>;
      },
      exportValue: (c) => (c.sla_breached ? "lewat SLA" : (c.sla_due_at || "")),
    },
    {
      key: "assigned_to", header: "PIC", sortable: true, hidden: true,
      render: (c) => <span className="text-sm">{c.assigned_to || "-"}</span>,
    },
    {
      key: "age_hours", header: "Umur (total · status)",
      render: (c) => <AgingCell ageHours={c.age_hours} stageAgeHours={c.stage_age_hours}
        slaHours={c.stage_sla_hours} state={c.sla_state} />,
      exportValue: (c) => `${Math.round(c.age_hours || 0)}j`,
    },
    {
      key: "created_at", header: "Masuk", sortable: true,
      render: (c) => <span className="text-xs text-muted-foreground">{fromNow(c.created_at)}</span>,
    },
  ], [labelOf]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "status", label: "Status", type: "multiselect",
        options: options("complaint_status")
          .map((o) => ({ ...o, hint: data?.counts?.[o.value] })) },
      { key: "priority", label: "Prioritas", type: "multiselect", options: options("priority") },
      { key: "category", label: "Kategori", type: "multiselect",
        options: options("complaint_category") },
      slaFilter(options("sla_state"),
        [{ value: "breached", label: "Lewat SLA penyelesaian komplain" }]),
      { key: "created", label: "Tanggal masuk", type: "daterange",
        fromKey: "created_from", toKey: "created_to" },
    ]} />
  );

  return (
    <div className="space-y-3">
      <DataTable testId={COMPLAINTS.table}
        testIds={{ row: COMPLAINTS.row, search: COMPLAINTS.search, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="komplain" exportName="komplain" onRefresh={load}
        searchPlaceholder="Cari subjek / pelanggan / unit / isi pesan…"
        onRowClick={(c) => setSelected(c.id)}
        bulkActions={[{
          key: "export", label: "Ekspor terpilih", testId: COMPLAINTS.bulkExport,
          onRun: (rows) => {
            downloadCsv(columns, rows, "komplain-terpilih");
            toast.success(`${rows.length} baris diekspor ke CSV.`);
          },
        }]}
        emptyTitle={activeCount || query.q ? "Tidak ada komplain yang cocok"
          : "Tidak ada komplain"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Komplain dari pembeli (via Portal) akan muncul di sini beserta SLA-nya."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : ""}
        emptyAction={activeCount || query.q ? () => reset() : null} />

      <ComplaintDetailSheet complaintId={selected} open={!!selected}
        onOpenChange={(v) => !v && setSelected(null)}
        onChanged={() => { load(); onChanged?.(); }} />
    </div>
  );
}
