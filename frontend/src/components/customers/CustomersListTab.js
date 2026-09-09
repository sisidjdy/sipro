import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import AgingCell from "@/components/patterns/AgingCell";
import AddCustomerDialog from "@/components/customers/AddCustomerDialog";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import { fromNow } from "@/utils/formatters";
import { downloadCsv } from "@/utils/tableCsv";
import { slaFilter } from "@/utils/agingFilter";
import api from "@/services/apiClient";
import { CUSTOMERS, DT } from "@/constants/testIds";

const KYC_OPTIONS = [
  { value: "pending", label: "KYC Pending" },
  { value: "submitted", label: "KYC Terkirim" },
];

/**
 * CustomersListTab — tabel pembeli (KYC). Klik baris → halaman kanonik `/customers/:id`.
 * Drawer detail lama dihapus: isinya (identitas, KYC, dokumen syarat, KPR, unit, komplain,
 * timeline) jauh melebihi satu layar — tempatnya halaman, bukan drawer (blueprint §2.3).
 */
export default function CustomersListTab() {
  const navigate = useNavigate();
  const { options } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { kyc_status: [], created_from: "", created_to: "", sla: "" },
    sort: "created_at", direction: "desc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/customers", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat customer.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const columns = useMemo(() => [
    {
      key: "name", header: "Nama", sortable: true, width: "24%",
      render: (c) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{c.name}</p>
          <p className="text-xs text-muted-foreground">{c.phone || "-"}</p>
        </div>
      ),
      exportValue: (c) => `${c.name} (${c.phone || "-"})`,
    },
    { key: "nik", header: "NIK", sortable: true, className: "tabular-nums" },
    { key: "occupation", header: "Pekerjaan", render: (c) => c.occupation || "-" },
    {
      key: "monthly_income", header: "Penghasilan/bln", sortable: true, align: "right",
      render: (c) => <MoneyText value={c.monthly_income} />,
      exportValue: (c) => c.monthly_income || 0,
    },
    {
      key: "kyc_status", header: "KYC", sortable: true,
      render: (c) => <StatusPill status={c.kyc_status}
        label={c.kyc_status === "submitted" ? "Terkirim" : "Pending"} />,
    },
    {
      key: "kyc_files", header: "Lampiran", align: "right",
      render: (c) => <span className="tabular-nums">{(c.kyc_files || []).length}</span>,
      exportValue: (c) => (c.kyc_files || []).length,
    },
    {
      key: "age_hours", header: "Umur data",
      render: (c) => <AgingCell ageHours={c.age_hours} stageAgeHours={c.stage_age_hours}
        slaHours={c.stage_sla_hours} state={c.sla_state} />,
      exportValue: (c) => `${Math.round(c.age_hours || 0)}j`,
    },
    {
      key: "created_at", header: "Ditambahkan", sortable: true,
      render: (c) => <span className="text-xs text-muted-foreground">{fromNow(c.created_at)}</span>,
    },
  ], []);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "kyc_status", label: "Status KYC", type: "multiselect",
        options: KYC_OPTIONS.map((o) => ({ ...o, hint: data?.counts?.[o.value] })) },
      slaFilter(options("sla_state")),
      { key: "created", label: "Ditambahkan", type: "daterange",
        fromKey: "created_from", toKey: "created_to" },
    ]} />
  );

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button data-testid={CUSTOMERS.addBtn} size="sm" onClick={() => setAddOpen(true)}>
          <UserPlus className="mr-1.5 h-4 w-4" /> Tambah Customer
        </Button>
      </div>
      <DataTable testId={CUSTOMERS.table}
        testIds={{ row: CUSTOMERS.row, search: CUSTOMERS.searchInput, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="pembeli" exportName="customer" onRefresh={load}
        searchPlaceholder="Cari nama / telepon / NIK / NPWP…"
        onRowClick={(c) => navigate(`/customers/${c.id}`)}
        bulkActions={[{
          key: "export", label: "Ekspor terpilih", testId: CUSTOMERS.bulkExport,
          onRun: (rows) => {
            downloadCsv(columns, rows, "customer-terpilih");
            toast.success(`${rows.length} baris diekspor ke CSV.`);
          },
        }]}
        emptyTitle={activeCount || query.q ? "Tidak ada pembeli yang cocok" : "Belum ada customer"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Tambah data pembeli (KYC) untuk keperluan legal (PPJB/AJB) dan pengajuan KPR."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : "Tambah Customer"}
        emptyAction={() => (activeCount || query.q ? reset() : setAddOpen(true))} />
      <AddCustomerDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
    </div>
  );
}
