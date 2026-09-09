import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import DataTable from "@/components/patterns/DataTable";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import StatusPill from "@/components/patterns/StatusPill";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { MASTERPLAN } from "@/constants/testIds";

/**
 * Tab UNIT — tabel unit dengan DUA kolom status (penjualan & pembangunan) sesuai permintaan
 * owner, plus filter cluster/status/tipe, sort, kolom pilihan, ekspor CSV.
 */
export default function UnitsTab({ projectId, clusters = [] }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // Filter awal boleh datang dari URL (tautan "Buka tabel terfilter" popup rincian, Fase 93).
  const [filters, setFilters] = useState({
    cluster_id: params.get("cluster_id") || "", status: params.get("status") || "",
    construction_status: params.get("construction_status") || "",
  });
  const [query, setQuery] = useState({ q: "", sort: "code", direction: "asc", skip: 0, limit: 25 });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/masterplan/units", {
        params: {
          project_id: projectId, cluster_id: filters.cluster_id || undefined,
          status: filters.status || undefined,
          construction_status: filters.construction_status || undefined,
          q: query.q || undefined, sort: query.sort, direction: query.direction,
          skip: query.skip, limit: query.limit,
        },
      });
      setRows(res.data.data || []);
      setTotal(res.data.total || 0);
      setSummary(res.data.summary || {});
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat unit.");
    } finally { setLoading(false); }
  }, [projectId, filters, query]);

  useEffect(() => { load(); }, [load]);

  const columns = [
    { key: "code", header: "Kode unit", sortable: true,
      render: (r) => <span className="font-medium">{r.code}</span> },
    { key: "cluster", header: "Cluster", sortable: true,
      render: (r) => r.cluster_code || "-", exportValue: (r) => r.cluster_code },
    { key: "block", header: "Blok", sortable: true },
    { key: "type", header: "Tipe", sortable: true },
    { key: "luas", header: "LT / LB (m²)", align: "right",
      render: (r) => `${r.luas_tanah ?? "-"} / ${r.luas_bangunan ?? "-"}`,
      exportValue: (r) => `${r.luas_tanah}/${r.luas_bangunan}` },
    { key: "corner", header: "Hook",
      render: (r) => (r.corner ? "Hook/sudut" : "–"),
      exportValue: (r) => (r.corner ? "ya" : "tidak") },
    { key: "price", header: "Harga", align: "right", sortable: true,
      render: (r) => formatIDR(r.price), exportValue: (r) => r.price },
    { key: "status", header: "Status penjualan", sortable: true,
      render: (r) => <StatusPill status={r.status} group="unit_status" />,
      exportValue: (r) => r.status_label },
    { key: "construction_status", header: "Status pembangunan", sortable: true,
      render: (r) => <StatusPill status={r.construction_status} group="construction_status" />,
      exportValue: (r) => r.construction_label },
    { key: "progress", header: "Progres", align: "right", sortable: true,
      render: (r) => `${r.construction_progress || 0}%`,
      exportValue: (r) => r.construction_progress },
    { key: "customer", header: "Pembeli",
      render: (r) => r.lead_name || "–", exportValue: (r) => r.lead_name },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-sm">
        {Object.entries(summary).map(([k, v]) => (
          <span key={k} className="rounded-md border bg-secondary px-2 py-1">
            <StatusPill status={k} group="unit_status" /> <strong className="tabular-nums">{v}</strong>
          </span>
        ))}
      </div>
      <DataTable
        testId={MASTERPLAN.unitTable}
        testIds={{ search: MASTERPLAN.unitSearch, row: MASTERPLAN.unitRow,
          export: MASTERPLAN.unitExport, columns: MASTERPLAN.unitColumns,
          pagination: MASTERPLAN.unitPagination }}
        columns={columns} rows={rows} total={total} query={query}
        onQueryChange={(p) => setQuery((q) => ({ ...q, ...p }))}
        loading={loading} error={error} onRefresh={load}
        onRowClick={(r) => navigate(`/units/${r.id}`)}
        searchPlaceholder="Cari kode unit / tipe / pembeli…" exportName="unit"
        emptyTitle="Belum ada unit"
        emptyDescription="Buat blok lalu gunakan tombol Buat unit di tab Struktur."
        filters={(
          <>
            <select data-testid={MASTERPLAN.unitFilterCluster} aria-label="Filter cluster"
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={filters.cluster_id}
              onChange={(e) => { setFilters({ ...filters, cluster_id: e.target.value });
                setQuery((q) => ({ ...q, skip: 0 })); }}>
              <option value="">Semua cluster</option>
              {clusters.map((c) => (
                <option key={c.id} value={c.id}>{c.code} · {c.name}</option>
              ))}
            </select>
            <div className="w-[170px]">
              {filters.status.includes(",") ? (
                <button type="button" data-testid={MASTERPLAN.unitFilterStatusChip}
                  className="flex h-9 w-full items-center justify-between rounded-md border bg-primary/5 px-2 text-xs font-medium text-primary"
                  title="Filter beberapa status dari popup rincian — klik untuk menghapus"
                  onClick={() => { setFilters({ ...filters, status: "" }); setQuery((q) => ({ ...q, skip: 0 }));
                    const next = new URLSearchParams(params); next.delete("status"); setParams(next, { replace: true }); }}>
                  <span className="truncate">Status: {filters.status.split(",").length} pilihan</span><span aria-hidden>×</span>
                </button>
              ) : (
                <ReferenceSelect group="unit_status" value={filters.status} allowEmpty
                  emptyLabel="Semua status jual" testId={MASTERPLAN.unitFilterStatus}
                  onChange={(v) => { setFilters({ ...filters, status: v });
                    setQuery((q) => ({ ...q, skip: 0 })); }} />
              )}
            </div>
            <div className="w-[180px]">
              <ReferenceSelect group="construction_status" value={filters.construction_status}
                allowEmpty emptyLabel="Semua status bangun" testId={MASTERPLAN.unitFilterBuild}
                onChange={(v) => { setFilters({ ...filters, construction_status: v });
                  setQuery((q) => ({ ...q, skip: 0 })); }} />
            </div>
          </>
        )} />
    </div>
  );
}
