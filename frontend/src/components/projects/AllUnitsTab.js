import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import ReserveDialog from "@/components/sales/ReserveDialog";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { MASTERPLAN } from "@/constants/testIds";

/**
 * AllUnitsTab — tabel unit LINTAS proyek (Fase 40).
 *
 * Sebelumnya unit hanya tampil sebagai kartu (grid) di layar “Deal & Unit”: tidak bisa dicari,
 * tidak bisa difilter per status bangun/bayar, tidak bisa diurutkan per harga, dan mustahil
 * dipakai kalau unitnya ratusan. Satu komponen ini dipakai dua tempat — Pembangunan (Papan
 * Unit) dan Customer & Kontrak (tab Unit) — sehingga angka & perilakunya tidak bisa berbeda.
 *
 * `showReserve`: menampilkan aksi Reservasi (hanya berguna untuk peran penjualan).
 */
export default function AllUnitsTab({ showReserve = false, onChanged }) {
  const navigate = useNavigate();
  const { options } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: {
      status: [], construction_status: [], payment_status: [], type: [], project_id: [],
    },
    sort: "code", direction: "asc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reserveUnit, setReserveUnit] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/units", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat unit.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/projects").then((r) => setProjects((r.data.data || [])
      .map((p) => ({ value: p.id, label: p.name })))).catch(() => setProjects([]));
  }, []);

  const counts = data?.counts || {};
  const columns = useMemo(() => [
    {
      key: "code", header: "Kode unit", sortable: true,
      render: (u) => (
        <div>
          <p className="font-medium text-primary">{u.code}</p>
          <p className="text-xs text-muted-foreground">{u.project_name || "-"}</p>
        </div>
      ),
    },
    { key: "type", header: "Tipe", sortable: true },
    {
      key: "cluster_code", header: "Cluster / Blok", sortable: true,
      render: (u) => `${u.cluster_code || "-"} / ${u.block || "-"}`,
      exportValue: (u) => `${u.cluster_code || "-"}/${u.block || "-"}`,
    },
    {
      key: "price", header: "Harga", sortable: true, align: "right",
      render: (u) => <MoneyText value={u.price} />, exportValue: (u) => u.price || 0,
    },
    {
      key: "status", header: "Status jual", sortable: true,
      render: (u) => <StatusPill status={u.status} group="unit_status" />,
    },
    {
      key: "construction_status", header: "Pembangunan", sortable: true,
      render: (u) => (
        <div className="space-y-1">
          <StatusPill status={u.construction_status || "not_started"} group="construction_status" />
          <p className="text-xs tabular-nums text-muted-foreground">
            {u.construction_progress || 0}%
          </p>
        </div>
      ),
      exportValue: (u) => `${u.construction_status || "-"} ${u.construction_progress || 0}%`,
    },
    {
      key: "payment_status", header: "Bayar", sortable: true,
      render: (u) => <StatusPill status={u.payment_status || "unpaid"}
        group="unit_payment_status" />,
    },
    {
      key: "lead_name", header: "Pemesan",
      render: (u) => u.lead_name || <span className="text-muted-foreground">—</span>,
    },
    ...(showReserve ? [{
      key: "aksi", header: "Aksi", align: "right", sticky: true, sticky: true,
      render: (u) => (u.status === "available" ? (
        <Button size="sm" data-testid={MASTERPLAN.unitReserveBtn}
          onClick={(e) => { e.stopPropagation(); setReserveUnit(u); }}>
          Reservasi
        </Button>
      ) : <span className="text-xs text-muted-foreground">—</span>),
      exportValue: () => "",
    }] : []),
  ], [showReserve]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "status", label: "Status jual", type: "multiselect",
        options: options("unit_status").map((o) => ({ ...o, hint: counts[o.value] })) },
      { key: "construction_status", label: "Pembangunan", type: "multiselect",
        options: options("construction_status") },
      { key: "payment_status", label: "Bayar", type: "multiselect",
        options: options("unit_payment_status") },
      { key: "project_id", label: "Proyek", type: "multiselect", options: projects },
    ]} />
  );

  return (
    <>
      <DataTable testId={MASTERPLAN.allUnitsTable} testIds={{ row: MASTERPLAN.unitRow }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="unit" exportName="unit" onRefresh={load}
        searchPlaceholder="Cari kode / tipe / blok / pemesan…"
        onRowClick={(u) => navigate(`/units/${u.id}`)}
        emptyTitle={activeCount || query.q ? "Tidak ada unit yang cocok" : "Belum ada unit"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Buat cluster → blok → unit dari halaman proyek."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : ""}
        emptyAction={() => reset()}
        bulkActions={[]} />
      {showReserve ? (
        <ReserveDialog mode="byUnit" unitId={reserveUnit?.id}
          unitLabel={reserveUnit ? `${reserveUnit.code} · ${reserveUnit.type}` : ""}
          open={!!reserveUnit} onOpenChange={(v) => !v && setReserveUnit(null)}
          onReserved={() => { load(); onChanged?.(); }} />
      ) : null}
      <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Building2 className="h-3.5 w-3.5" /> Klik baris untuk membuka Unit 360
        (ringkasan, penjualan, pembangunan, dokumen, riwayat).
      </p>
    </>
  );
}
