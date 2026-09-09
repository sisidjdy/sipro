import React, { useCallback, useEffect, useMemo, useState } from "react";

import DataTable from "@/components/patterns/DataTable";
import MetricDetailDialog from "@/components/bi/MetricDetailDialog";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { BI, DT } from "@/constants/testIds";

/**
 * MetricDictionaryTab — KAMUS METRIK di dalam aplikasi.
 *
 * Kenapa ini layar, bukan dokumen: pertanyaan “angka ini dari mana?” muncul justru saat orang
 * sedang melihat angkanya. Di sini setiap metrik menyebut kode, rumus, satuan, dashboard
 * pemakainya, data yang dibutuhkannya, dan bisa langsung dibuka rinciannya — termasuk metrik
 * yang datanya BELUM ADA (itu peta pekerjaan, bukan hal yang disembunyikan).
 */
export default function MetricDictionaryTab() {
  const { labelOf } = useReference();
  const { query, setQuery } = useListQuery({
    filters: {}, sort: "code", direction: "asc", limit: 50,
  });
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/analytics/metrics");
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kamus metrik.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (row) => {
    try {
      const res = await api.get(`/analytics/metric/${row.code}`);
      setDetail(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rincian metrik.");
    }
  };

  const filtered = useMemo(() => {
    const q = (query.q || "").toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => `${r.code} ${r.label} ${r.formula} ${r.persona}`
      .toLowerCase().includes(q));
  }, [rows, query.q]);

  const columns = useMemo(() => [
    { key: "code", header: "Kode", width: "90px",
      render: (r) => <span className="font-mono text-xs">{r.code}</span> },
    { key: "label", header: "Nama metrik",
      render: (r) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{r.label}</p>
          <p className="text-xs text-muted-foreground">{r.formula}</p>
        </div>
      ) },
    { key: "persona", header: "Dashboard",
      render: (r) => labelOf("metric_persona", r.persona),
      exportValue: (r) => r.persona },
    { key: "unit", header: "Satuan", render: (r) => labelOf("metric_unit", r.unit) },
    { key: "requires", header: "Butuh data",
      render: (r) => (
        <span className="text-xs text-muted-foreground">{(r.requires || []).join(", ")}</span>
      ),
      exportValue: (r) => (r.requires || []).join("|") },
    { key: "snapshot", header: "Snapshot harian",
      render: (r) => (r.snapshot ? "ya" : "tidak") },
  ], [labelOf]);

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Setiap angka di lima dashboard berasal dari salah satu metrik di bawah — satu metrik,
        satu rumus, satu tempat. Klik satu baris untuk melihat nilai & rinciannya sekarang.
      </p>
      <DataTable testId={BI.dictTable} testIds={{ row: BI.dictRow, search: DT.search }}
        columns={columns} rows={filtered} total={filtered.length}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        onRowClick={openDetail} onRefresh={load} label="metrik"
        searchPlaceholder="Cari kode / nama / rumus metrik…" exportName="kamus-metrik"
        emptyTitle="Kamus metrik kosong"
        emptyDescription="Registry metrik tidak mengembalikan apa pun — laporkan ke pengelola sistem." />
      <MetricDetailDialog metric={detail} open={!!detail}
        onOpenChange={(v) => !v && setDetail(null)} />
    </div>
  );
}
