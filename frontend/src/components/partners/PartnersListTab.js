import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Handshake, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import PartnerFormDialog from "@/components/partners/PartnerFormDialog";
import PartnerStatusDialog from "@/components/partners/PartnerStatusDialog";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { downloadCsv } from "@/utils/tableCsv";
import { fromNow } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PARTNERS, DT } from "@/constants/testIds";

/**
 * PartnersListTab — master **Mitra** sebagai tabel pro (Fase 42, `docs/v2/25_PARTNER_SPEC.md`).
 *
 * Sebelum fase ini yang ada hanyalah "Master Agen" di dalam menu Marketing Fee: nama, jenis,
 * bank, status — tanpa kontrak, tanpa aturan fee, tanpa angka kinerja. Akibatnya pertanyaan
 * paling dasar tidak bisa dijawab: "mitra ini kontraknya masih berlaku? sudah setor berapa
 * lead? fee-nya masih nyangkut berapa?".
 */
export default function PartnersListTab() {
  const navigate = useNavigate();
  const { options, labelOf } = useReference();
  const { can } = useAuth();
  // Izin diambil dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis
  // ulang di layar. Matriks RBAC bisa diubah admin lewat Pusat Konfigurasi; daftar peran
  // hardcode membuat tombol berbeda dengan jawaban server — tombol mati (403) atau
  // tombol yang seharusnya ada tapi hilang.
  const canCreate = can("partners", "create");
  const canUpdate = can("partners", "update");
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { partner_kind: [], status: [] },
    sort: "created_at", direction: "desc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formFor, setFormFor] = useState(null);
  const [statusFor, setStatusFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/partners", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar mitra.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const columns = useMemo(() => [
    {
      key: "name", header: "Mitra", sortable: true, width: "24%",
      render: (p) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{p.name}</p>
          <p className="text-xs text-muted-foreground">
            {p.code} · {p.phone || "tanpa nomor"}
          </p>
        </div>
      ),
      exportValue: (p) => `${p.name} (${p.code})`,
    },
    {
      key: "partner_kind", header: "Jenis", sortable: true,
      render: (p) => (
        <div>
          <p className="text-sm">{labelOf("partner_kind", p.partner_kind)}</p>
          <p className="text-xs text-muted-foreground">
            {labelOf("partner_entity_type", p.entity_type)}
          </p>
        </div>
      ),
      exportValue: (p) => labelOf("partner_kind", p.partner_kind),
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (p) => <StatusPill status={p.status} group="agent_status" />,
    },
    {
      key: "contract_ok", header: "Kontrak",
      render: (p) => (p.contract_ok ? (
        <span className="text-xs text-emerald-700">
          berlaku s/d {String(p.contract?.end_date || "—").slice(0, 10)}
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700"
          title={p.contract_note || ""}>
          <AlertTriangle className="h-3.5 w-3.5" /> {p.contract_note || "belum lengkap"}
        </span>
      )),
      exportValue: (p) => (p.contract_ok ? "berlaku" : (p.contract_note || "belum lengkap")),
    },
    {
      key: "rules_count", header: "Aturan fee", align: "right",
      render: (p) => (p.rules_count ? (
        <span className="text-sm tabular-nums">{p.rules_count} khusus</span>
      ) : (
        <span className="text-xs text-muted-foreground">pakai aturan umum</span>
      )),
      exportValue: (p) => p.rules_count || 0,
    },
    {
      key: "leads", header: "Lead", align: "right",
      render: (p) => <span className="text-sm tabular-nums">{p.stats?.leads ?? 0}</span>,
      exportValue: (p) => p.stats?.leads ?? 0,
    },
    {
      key: "fee_total", header: "Fee disetujui", sortable: true, align: "right",
      render: (p) => <MoneyText value={p.fee_total} short />,
      exportValue: (p) => p.fee_total || 0,
    },
    {
      key: "fee_outstanding", header: "Sisa utang fee", align: "right",
      render: (p) => <MoneyText value={(p.fee_total || 0) - (p.fee_paid || 0)} short
        className={(p.fee_total || 0) - (p.fee_paid || 0) ? "text-amber-700" : ""} />,
      exportValue: (p) => (p.fee_total || 0) - (p.fee_paid || 0),
    },
    {
      key: "last_lead_at", header: "Lead terakhir", hidden: true,
      render: (p) => (
        <span className="text-xs text-muted-foreground">
          {p.stats?.last_lead_at ? fromNow(p.stats.last_lead_at) : "belum ada"}
        </span>
      ),
      exportValue: (p) => p.stats?.last_lead_at || "",
    },
    {
      key: "actions", header: "", sticky: true,
      render: (p) => (canUpdate ? (
        <Button data-testid={PARTNERS.statusBtn} data-partner={p.id} size="sm" variant="outline"
          aria-label={`Ubah status mitra ${p.name}`}
          onClick={(e) => { e.stopPropagation(); setStatusFor(p); }}>
          Status
        </Button>
      ) : null),
      exportValue: () => "",
    },
  ], [labelOf, canUpdate]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "partner_kind", label: "Jenis mitra", type: "multiselect",
        options: options("partner_kind") },
      { key: "status", label: "Status", type: "multiselect",
        options: options("agent_status")
          .map((o) => ({ ...o, hint: data?.counts?.[o.value] })) },
    ]} />
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Mitra penyumbang lead di luar tim inhouse. Status <em>ditangguhkan</em>,
          <em> kontrak kedaluwarsa</em>, atau <em>daftar hitam</em> memblokir lead &amp; fee
          BARU — tagihan yang sudah disetujui tetap menjadi utang.
        </p>
        {canCreate ? (
          <Button data-testid={PARTNERS.addBtn} size="sm" onClick={() => setFormFor({})}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Mitra
          </Button>
        ) : null}
      </div>

      <DataTable testId={PARTNERS.table}
        testIds={{ row: PARTNERS.row, search: PARTNERS.search, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="mitra" exportName="mitra" onRefresh={load}
        searchPlaceholder="Cari nama / kode / perusahaan / nomor…"
        onRowClick={(p) => navigate(`/partners/${p.id}`)}
        bulkActions={[{
          key: "export", label: "Ekspor terpilih",
          onRun: (rows) => {
            downloadCsv(columns, rows, "mitra-terpilih");
            toast.success(`${rows.length} baris diekspor ke CSV.`);
          },
        }]}
        emptyTitle={activeCount || query.q ? "Tidak ada mitra yang cocok" : "Belum ada mitra"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Daftarkan mitra (agen, broker, aggregator, referral) beserta kontraknya supaya lead & fee-nya bisa dipertanggungjawabkan."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : (canCreate ? "Tambah Mitra" : "")}
        emptyAction={activeCount || query.q ? () => reset()
          : (canCreate ? () => setFormFor({}) : null)} />

      <PartnerFormDialog partner={formFor} open={!!formFor}
        onOpenChange={(v) => !v && setFormFor(null)} onDone={load} />
      <PartnerStatusDialog partner={statusFor} open={!!statusFor}
        onOpenChange={(v) => !v && setStatusFor(null)} onDone={load} />
    </div>
  );
}
