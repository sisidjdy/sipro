import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import { EMPTY_UNIT_TYPE, UnitTypeFormDialog } from "@/components/config/UnitTypeFormDialog";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { CONFIG } from "@/constants/testIds";

const EMPTY = EMPTY_UNIT_TYPE;

/** Master TIPE UNIT — dasar harga & spesifikasi unit (dipakai generator unit & SPR). */
export default function UnitTypePanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState({ q: "", sort: "code", direction: "asc", skip: 0, limit: 50 });
  const [form, setForm] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/catalog/unit-types");
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat tipe unit.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = rows.filter((r) => {
    const q = (query.q || "").toLowerCase();
    return !q || `${r.code} ${r.name}`.toLowerCase().includes(q);
  });

  const columns = [
    { key: "code", header: "Kode", sortable: true,
      render: (r) => <span className="font-mono text-xs">{r.code}</span> },
    { key: "name", header: "Tipe", sortable: true,
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-medium">{r.name}</span>
          {r.needs_review ? (
            <span className="inline-flex items-center gap-1 rounded border bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-800">
              <AlertTriangle className="h-3 w-3" /> perlu ditinjau
            </span>
          ) : null}
        </div>
      ) },
    { key: "building_area", header: "Luas bangunan (m²)", align: "right", sortable: true,
      render: (r) => r.building_area ?? "belum diisi" },
    { key: "land_area_std", header: "Luas tanah standar (m²)", align: "right", sortable: true,
      render: (r) => r.land_area_std ?? "belum diisi" },
    { key: "base_price", header: "Harga dasar", align: "right", sortable: true,
      render: (r) => (r.base_price ? formatIDR(r.base_price)
        : <span className="text-muted-foreground">belum diisi</span>),
      exportValue: (r) => r.base_price },
    { key: "units_count", header: "Jumlah unit", align: "right", sortable: true },
    { key: "actions", header: "Aksi", align: "right", sticky: true,
      render: (r) => (
        <Button data-testid={CONFIG.typeEdit} size="sm" variant="ghost"
          onClick={() => setForm({ ...EMPTY, ...r })}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ), exportValue: () => "" },
  ];

  return (
    <div data-testid={CONFIG.typePanel} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Tipe hasil migrasi data lama ditandai <strong>perlu ditinjau</strong> bila luas/harga
          tidak bisa dipastikan — sistem tidak mengarang angka.
        </p>
        <Button data-testid={CONFIG.typeAdd} size="sm" onClick={() => setForm({ ...EMPTY })}>
          <Plus className="mr-1.5 h-4 w-4" /> Tipe unit baru
        </Button>
      </div>
      <DataTable
        testId="config-type-table"
        testIds={{ search: "config-type-search", row: CONFIG.typeRow,
          export: "config-type-export", columns: "config-type-columns" }}
        columns={columns} rows={filtered} total={filtered.length} query={query}
        onQueryChange={(p) => setQuery((q) => ({ ...q, ...p }))}
        loading={loading} error={error} onRefresh={load}
        searchPlaceholder="Cari tipe unit…" exportName="tipe-unit"
        emptyTitle="Belum ada tipe unit" />

      <UnitTypeFormDialog form={form} setForm={setForm} onSaved={load} />
    </div>
  );
}
