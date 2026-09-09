import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Eye, HandCoins, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import AgingCell from "@/components/patterns/AgingCell";
import AgingBuckets from "@/components/finance/AgingBuckets";
import ReceiptDialog from "@/components/finance/ReceiptDialog";
import ArDetailSheet from "@/components/finance/ArDetailSheet";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR } from "@/utils/formatters";
import { downloadCsv } from "@/utils/tableCsv";
import { slaFilter } from "@/utils/agingFilter";
import api from "@/services/apiClient";
import { FINANCE, DT } from "@/constants/testIds";

/**
 * ArPanel — daftar piutang (AR) sebagai tabel pro (US-40-1 & US-40-4).
 *
 * Yang diperbaiki di Fase 40d:
 *   * dulu SELURUH tagihan dikirim tanpa paginasi, tanpa cari, tanpa filter status, dan
 *     tanpa sort — kasir dengan 300 tagihan mustahil menemukan “sisa terbesar yang jatuh
 *     tempo”; kini semuanya server-side (`/finance/ar`);
 *   * KPI “AR Outstanding” di Beranda menaut ke `?tab=ar&status=unpaid,partial`, dan filter
 *     itu dibaca dari URL oleh panel ini, sehingga angka KPI bisa ditelusuri sampai barisnya;
 *   * kolom umur (aging) ditambahkan agar penagihan bisa diurutkan berdasarkan kelambatan.
 *
 * Aksi lama dipertahankan seluruhnya: Detail (riwayat termin) dan Terima Bayar (kwitansi),
 * termasuk kolom Titipan pelanggan.
 */
export default function ArPanel() {
  const { options } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { status: [], created_from: "", created_to: "", sla: "" },
    sort: "created_at", direction: "desc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [aging, setAging] = useState(null);
  const [deposits, setDeposits] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [receiptDeal, setReceiptDeal] = useState(null);
  const [detailDealId, setDetailDealId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [a, ag, dep] = await Promise.all([
        api.get("/finance/ar", { params: apiParams }),
        api.get("/finance/ar/aging"),
        api.get("/finance/ar/deposits"),
      ]);
      setData(a.data);
      setAging(ag.data.data || null);
      // Titipan ditampilkan berdampingan dengan piutang supaya kasir langsung tahu ada
      // dana pembeli yang belum dialokasikan (Fase 26).
      setDeposits(Object.fromEntries((dep.data.data || [])
        .map((d) => [d.deal_id, Number(d.balance || 0)])));
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data piutang (AR).");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const columns = useMemo(() => [
    {
      key: "unit_code", header: "Unit", sortable: true,
      render: (r) => <span className="font-medium">{r.unit_code || "-"}</span>,
    },
    { key: "lead_name", header: "Pembeli", sortable: true,
      render: (r) => r.lead_name || "-" },
    { key: "scheme_name", header: "Skema", hidden: true,
      render: (r) => <span className="text-muted-foreground">{r.scheme_name || "-"}</span> },
    {
      key: "total", header: "Total", sortable: true, align: "right",
      render: (r) => <MoneyText value={r.total} />, exportValue: (r) => r.total || 0,
    },
    {
      key: "paid", header: "Terbayar", sortable: true, align: "right",
      render: (r) => <MoneyText value={r.paid} className="text-emerald-700" />,
      exportValue: (r) => r.paid || 0,
    },
    {
      key: "outstanding", header: "Sisa", sortable: true, align: "right",
      render: (r) => <MoneyText value={r.outstanding} className="font-medium" />,
      exportValue: (r) => r.outstanding || 0,
    },
    {
      key: "buyer_total", header: "Total tagihan pembeli", align: "right",
      render: (r) => (
        <span data-testid="ar-buyer-total" className="tabular-nums">
          <MoneyText value={(r.total || 0) + (r.cost_total || 0)} className="font-medium" />
          <span className="block text-[10px] text-muted-foreground">
            unit {formatIDR(r.unit_total ?? ((r.total || 0) - (r.addon_total || 0)))}
            {r.addon_total ? ` + add-on ${formatIDR(r.addon_total)}` : ""}
            {r.cost_total ? ` + biaya ${formatIDR(r.cost_total)}` : ""}
          </span>
        </span>
      ),
      exportValue: (r) => (r.total || 0) + (r.cost_total || 0),
    },
    {
      key: "cost_outstanding", header: "Piutang biaya", align: "right",
      render: (r) => (r.cost_total ? (
        <span data-testid="ar-cost-outstanding" title={(r.cost_invoice_numbers || []).join(", ")}
          className="tabular-nums text-xs">
          <MoneyText value={r.cost_outstanding} />
          <span className="block text-[10px] text-muted-foreground">dari {formatIDR(r.cost_total)}</span>
        </span>
      ) : <span className="text-muted-foreground">—</span>),
      exportValue: (r) => r.cost_outstanding || 0,
    },
    {
      key: "deposit", header: "Titipan", align: "right",
      render: (r) => (deposits[r.deal_id] ? (
        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
          {formatIDR(deposits[r.deal_id])}
        </span>
      ) : <span className="text-muted-foreground">—</span>),
      exportValue: (r) => deposits[r.deal_id] || 0,
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (r) => <StatusPill status={r.status} group="ar_status" />,
    },
    {
      key: "age_hours", header: "Umur (total · status)",
      render: (r) => <AgingCell ageHours={r.age_hours} stageAgeHours={r.stage_age_hours}
        slaHours={r.stage_sla_hours} state={r.sla_state} />,
      exportValue: (r) => `${Math.round(r.age_hours || 0)}j`,
    },
    {
      key: "aksi", header: "Aksi", align: "right", sticky: true, sticky: true,
      render: (r) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          <Button size="sm" variant="outline" data-testid={FINANCE.arDetailBtn}
            data-deal={r.deal_id} aria-label={`Detail piutang unit ${r.unit_code || "-"}`}
            onClick={() => setDetailDealId(r.deal_id)}>
            <Eye className="mr-1 h-3.5 w-3.5" /> Detail
          </Button>
          {r.outstanding > 0 ? (
            <Button size="sm" data-testid={FINANCE.receiptBtn} data-deal={r.deal_id}
              aria-label={`Terima pembayaran unit ${r.unit_code || "-"}`}
              onClick={() => setReceiptDeal({ deal_id: r.deal_id, unit_code: r.unit_code,
                outstanding: r.outstanding })}>
              <HandCoins className="mr-1 h-3.5 w-3.5" /> Terima Bayar
            </Button>
          ) : null}
        </div>
      ),
      exportValue: () => "",
    },
  ], [deposits]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "status", label: "Status", type: "multiselect",
        options: options("ar_status").map((o) => ({ ...o, hint: data?.counts?.[o.value] })) },
      slaFilter(options("sla_state")),
      { key: "created", label: "Tanggal terbit", type: "daterange",
        fromKey: "created_from", toKey: "created_to" },
    ]} />
  );

  return (
    <div data-testid={FINANCE.arPanel} className="space-y-4">
      <AgingBuckets buckets={aging?.buckets}
        title={`Aging Piutang · Total ${formatIDR(aging?.total || 0)} · belum tertagih ${aging?.outstanding_pct ?? 0}% dari total tagihan`} />

      <DataTable testId={FINANCE.arTable}
        testIds={{ row: FINANCE.arRow, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="tagihan" exportName="piutang-ar" onRefresh={load}
        searchPlaceholder="Cari unit / pembeli / skema…"
        bulkActions={[{
          key: "export", label: "Ekspor terpilih", testId: FINANCE.arBulkExport,
          onRun: (rows) => {
            downloadCsv(columns, rows, "piutang-terpilih");
            toast.success(`${rows.length} baris diekspor ke CSV.`);
          },
        }]}
        emptyTitle={activeCount || query.q ? "Tidak ada tagihan yang cocok"
          : "Belum ada jadwal AR"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Jadwal AR otomatis dibuat saat unit di-booking. Booking unit di Customer & Kontrak untuk memulai."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : ""}
        emptyAction={activeCount || query.q ? () => reset() : null}
        footer={!loading && !error && (data?.data || []).length ? (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Wallet className="h-3.5 w-3.5" />
            Angka pada kolom Sisa adalah sisa kewajiban kontrak; titipan belum dialokasikan ke
            termin sampai diproses di tab Titipan.
          </p>
        ) : null} />

      <ReceiptDialog open={!!receiptDeal} onOpenChange={(v) => !v && setReceiptDeal(null)}
        deal={receiptDeal} onDone={load} />
      <ArDetailSheet dealId={detailDealId} open={!!detailDealId}
        onOpenChange={(v) => !v && setDetailDealId(null)} onChanged={load} />
    </div>
  );
}
