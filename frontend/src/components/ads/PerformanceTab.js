import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { Link } from "react-router-dom";

import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import KpiCard from "@/components/patterns/KpiCard";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";
import MoneyText from "@/components/patterns/MoneyText";
import StatusPill from "@/components/patterns/StatusPill";
import { CostMetric, CostStatusBadge, SourceLabels } from "@/components/ads/CostStatus";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR, formatNumber } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ADS, DT, P93 } from "@/constants/testIds";

/**
 * PerformanceTab — **kinerja kampanye**: biaya, lead, kualifikasi, booking, pendapatan,
 * CPL / biaya per lead terkualifikasi / CAC / ROAS (Fase 43 §8).
 *
 * ATURAN KEJUJURAN yang dipegang layar ini (dan diuji gate):
 *  1. Kampanye tanpa biaya pada rentang → metrik biaya ditulis “belum lengkap”, BUKAN Rp 0.
 *     Menampilkan 0 akan membuat kampanye yang biayanya belum diinput terlihat paling efisien.
 *  2. Biaya sebagian hari → lencana “Biaya belum lengkap (x/y hari)” supaya pembaca tahu
 *     angkanya masih akan berubah.
 *  3. Setiap angka biaya membawa label asalnya (manual / impor CSV / tarikan API).
 *  4. Lead yang nama kampanyenya tidak terdaftar DILAPORKAN di bawah tabel — bukan dibuang,
 *     supaya total di layar ini bisa direkonsiliasi dengan Pipeline Lead.
 */
export default function PerformanceTab() {
  const { options, labelOf } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { platform: "", status: "", date_from: "", date_to: "" },
    sort: "", direction: "desc", limit: 50,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [drillTarget, setDrillTarget] = useState(null);
  const drill = (sub, label) => setDrillTarget({ key: `ads:${sub}`, label, params: {
    date_from: data?.range?.from, date_to: data?.range?.to, platform: apiParams.platform, status: apiParams.status } });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/ads/performance", { params: apiParams });
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kinerja kampanye.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const t = data?.totals || {};
  const rows = data?.rows || [];
  const unmatched = data?.unmatched || { leads: 0, campaign_values: [] };

  const columns = useMemo(() => [
    {
      key: "name", header: "Kampanye", width: "22%",
      render: (r) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{r.name}</p>
          <p className="text-xs text-muted-foreground">
            {r.platform_label} · {labelOf("campaign_objective", r.objective)}
          </p>
        </div>
      ),
      exportValue: (r) => r.name,
    },
    {
      key: "status", header: "Status",
      render: (r) => <StatusPill status={r.status} group="campaign_status" />,
    },
    {
      key: "spend", header: "Biaya", align: "right",
      render: (r) => (
        <div className="space-y-1 text-right">
          {/* Biaya BELUM diinput bukan "Rp 0": menulis Rp 0 membuat kampanye yang biayanya
              belum masuk terlihat paling murah di tabel yang sama. */}
          <CostMetric value={r.cost_status === "missing" ? null : r.spend}
            render={(v) => <MoneyText value={v} short />}
            note={r.cost_note || "biaya belum diinput untuk rentang ini"} />
          <CostStatusBadge status={r.cost_status} spendDays={r.spend_days}
            expectedDays={r.expected_days} />
        </div>
      ),
      exportValue: (r) => (r.cost_status === "missing" ? "" : r.spend),
    },
    {
      key: "sources", header: "Asal angka",
      render: (r) => <SourceLabels sources={r.sources} />,
      exportValue: (r) => (r.sources || []).join("|"),
    },
    {
      key: "leads", header: "Lead", align: "right",
      render: (r) => (
        <div className="text-right">
          <Link to={`/leads?q=${encodeURIComponent(r.name)}`} data-drill="leads"
            className="text-sm font-medium tabular-nums text-primary hover:underline">
            {formatNumber(r.leads)}
          </Link>
          <p className="text-xs text-muted-foreground">
            {r.leads_platform ? `platform: ${formatNumber(r.leads_platform)}` : "—"}
          </p>
        </div>
      ),
      exportValue: (r) => r.leads,
    },
    {
      key: "qualified", header: "Terkualifikasi", align: "right",
      render: (r) => (
        <div className="text-right">
          <span className="text-sm tabular-nums">{formatNumber(r.qualified)}</span>
          <p className="text-xs text-muted-foreground">
            {r.qualified_rate === null ? "—" : `${r.qualified_rate}%`}
          </p>
        </div>
      ),
      exportValue: (r) => r.qualified,
    },
    {
      key: "booked", header: "Booking", align: "right",
      render: (r) => (
        <div className="text-right">
          <span className="text-sm tabular-nums">{formatNumber(r.booked)}</span>
          <p className="text-xs text-muted-foreground">
            {r.booking_rate === null ? "—" : `${r.booking_rate}%`}
          </p>
        </div>
      ),
      exportValue: (r) => r.booked,
    },
    {
      key: "cpl", header: "CPL", align: "right",
      render: (r) => <CostMetric value={r.cpl} render={(v) => formatIDR(v)}
        note={r.cost_note || ""} />,
      exportValue: (r) => r.cpl ?? "",
    },
    {
      key: "cost_per_qualified", header: "Biaya/terkualifikasi", align: "right",
      render: (r) => <CostMetric value={r.cost_per_qualified} render={(v) => formatIDR(v)} />,
      exportValue: (r) => r.cost_per_qualified ?? "",
    },
    {
      key: "cac", header: "CAC", align: "right",
      render: (r) => <CostMetric value={r.cac} render={(v) => formatIDR(v)} />,
      exportValue: (r) => r.cac ?? "",
    },
    {
      key: "revenue", header: "Pendapatan", align: "right", hidden: true,
      render: (r) => <MoneyText value={r.revenue} short />,
      exportValue: (r) => r.revenue || 0,
    },
    {
      key: "roas", header: "ROAS", align: "right",
      render: (r) => <CostMetric value={r.roas} render={(v) => `${v}×`} />,
      exportValue: (r) => r.roas ?? "",
    },
    {
      key: "budget_used_pct", header: "Anggaran terpakai", align: "right", hidden: true,
      render: (r) => (r.budget_used_pct === null || r.budget_used_pct === undefined
        ? <span className="text-xs text-muted-foreground">tanpa anggaran</span>
        : <span className="text-sm tabular-nums">{r.budget_used_pct}%</span>),
      exportValue: (r) => r.budget_used_pct ?? "",
    },
  ], [labelOf]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "platform", label: "Platform", type: "select", options: options("ad_platform") },
      { key: "status", label: "Status kampanye", type: "select",
        options: options("campaign_status") },
      { key: "range", label: "Rentang tanggal", type: "daterange",
        fromKey: "date_from", toKey: "date_to" },
    ]} />
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Rentang: <strong>{data?.range?.from || "…"} → {data?.range?.to || "…"}</strong>. Lead
        dicocokkan ke kampanye lewat ID platform (kalau ada) atau nama kampanye pada lead —
        angka lead di sini berasal dari pipeline yang sama dengan halaman Lead.
      </p>

      <div data-testid={ADS.perfKpi} className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <KpiCard label="Biaya iklan" value={<MoneyText value={t.spend} short />} testId={`${P93.adsKpi}-spend`}
          hint={`${t.campaigns || 0} kampanye`} onOpen={() => drill("spend", "Biaya iklan per kampanye")} />
        <KpiCard label="Lead" value={formatNumber(t.leads || 0)} tone="sky" to="/leads" testId={`${P93.adsKpi}-leads`}
          drillLabel="Buka pipeline" onOpen={() => drill("leads", "Lead dari kampanye")} />
        <KpiCard label="Terkualifikasi" value={formatNumber(t.qualified || 0)} tone="amber" testId={`${P93.adsKpi}-qualified`}
          hint={t.qualified_rate === null ? "—" : `${t.qualified_rate}% dari lead`}
          onOpen={() => drill("qualified", "Lead terkualifikasi")} />
        <KpiCard label="CPL" testId={`${P93.adsKpi}-cpl`}
          value={t.cpl ? formatIDR(t.cpl) : "belum lengkap"} tone="primary"
          hint={t.cpl ? "biaya ÷ lead" : t.cost_note || "data biaya belum lengkap"}
          onOpen={() => drill("spend", "CPL — biaya iklan per kampanye (pembilang)")} />
        <KpiCard label="CAC" value={t.cac ? formatIDR(t.cac) : "belum lengkap"} tone="rose" testId={`${P93.adsKpi}-cac`}
          hint={t.cac ? "biaya ÷ booking" : "butuh biaya + booking"}
          onOpen={() => drill("booked", "CAC — lead yang booking (penyebut)")} />
        <KpiCard label="ROAS" value={t.roas ? `${t.roas}×` : "belum lengkap"} tone="emerald" testId={`${P93.adsKpi}-roas`}
          hint={t.roas ? "pendapatan ÷ biaya" : "butuh biaya + pendapatan"}
          onOpen={() => drill("booked", "ROAS — lead yang booking (pendapatan)")} />
      </div>
      <DrilldownDialog target={drillTarget} onOpenChange={(o) => { if (!o) setDrillTarget(null); }} />

      {t.campaigns_without_cost || t.campaigns_partial_cost ? (
        <div data-testid={ADS.costWarning}
          className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3
            text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            <strong>Data biaya belum lengkap.</strong> {t.campaigns_without_cost || 0} kampanye
            belum punya biaya sama sekali dan {t.campaigns_partial_cost || 0} baru terisi
            sebagian hari pada rentang ini. Karena itu CPL/CAC/ROAS untuk kampanye tersebut
            dikosongkan — bukan ditulis nol. Isi biayanya di tab <strong>Biaya Iklan</strong>.
          </p>
        </div>
      ) : null}

      <DataTable testId={ADS.perfTable}
        testIds={{ row: ADS.perfRow, pagination: DT.pagination }}
        columns={columns} rows={rows} total={rows.length}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="kampanye" exportName="kinerja-kampanye" onRefresh={load}
        searchPlaceholder=""
        emptyTitle={activeCount ? "Tidak ada kampanye yang cocok" : "Belum ada kampanye"}
        emptyDescription={activeCount
          ? "Longgarkan filter atau lebarkan rentang tanggalnya."
          : "Daftarkan kampanye di tab Kampanye, lalu isi biayanya — setelah itu CPL, CAC, dan ROAS bisa dihitung dari data nyata."}
        emptyActionLabel={activeCount ? "Reset filter" : ""}
        emptyAction={activeCount ? () => reset() : null} />

      {unmatched.leads ? (
        <p className="flex items-start gap-2 rounded-lg border bg-card p-3 text-xs
          text-muted-foreground shadow-[var(--shadow-card)]">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <strong>{unmatched.leads} lead</strong> membawa nama kampanye yang belum terdaftar
            ({unmatched.campaign_values.slice(0, 4).join(", ")}
            {unmatched.campaign_values.length > 4 ? ", …" : ""}), jadi tidak ikut dihitung di
            tabel ini. Daftarkan kampanyenya dengan nama yang sama persis agar leadnya
            tersambung ke biaya.
          </span>
        </p>
      ) : null}
    </div>
  );
}
