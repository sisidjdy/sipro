import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Download, Plus, RefreshCw } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import KpiCard from "@/components/patterns/KpiCard";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";
import MoneyText from "@/components/patterns/MoneyText";
import ChartFrame from "@/components/patterns/ChartFrame";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import SpendEntryDialog from "@/components/ads/SpendEntryDialog";
import SpendImportDialog from "@/components/ads/SpendImportDialog";
import { SourceLabels } from "@/components/ads/CostStatus";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR, formatNumber } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ADS, DT, P93 } from "@/constants/testIds";

/**
 * SpendTab — **biaya iklan harian** (Fase 43 §5).
 *
 * Tiga cara angka masuk, dan ketiganya selalu diberi label asalnya: input manual, impor CSV
 * (idempoten, dengan pratinjau), dan tarikan API platform (hanya bila kredensial ada — kalau
 * tidak, tombolnya menjelaskan kenapa belum bisa, bukan gagal diam-diam).
 *
 * Satu baris = satu (platform × kampanye × adset × iklan × tanggal). Mengirim tanggal yang
 * sama dua kali MEMPERBARUI baris itu dan menyimpan nilai lamanya di riwayat — biaya tidak
 * boleh berubah tanpa jejak, dan tidak boleh terhitung dua kali.
 */
export default function SpendTab() {
  const { options, labelOf } = useReference();
  const { can } = useAuth();
  const canCreate = can("ads", "create");
  const canManage = can("ads", "manage");
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { platform: [], source: [], campaign_id: "", date_from: "", date_to: "" },
    sort: "date", direction: "desc", limit: 25,
  });
  const [period, setPeriod] = useState("daily");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [entryOpen, setEntryOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [drillTarget, setDrillTarget] = useState(null);
  const drill = (sub, label) => setDrillTarget({ key: `ads:${sub}`, label, params: {
    date_from: data?.data?.range?.from || apiParams.date_from, date_to: data?.data?.range?.to || apiParams.date_to,
    platform: Array.isArray(apiParams.platform) ? apiParams.platform.join(",") : apiParams.platform,
    campaign_id: apiParams.campaign_id } });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/ads/spend", { params: { ...apiParams, period } });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat biaya iklan.");
    } finally { setLoading(false); }
  }, [apiParams, period]);

  useEffect(() => { load(); }, [load]);

  const sync = async (platform) => {
    setSyncing(true);
    try {
      const res = await api.post("/ads/sync", { platform });
      const d = res.data.data || {};
      toast.success(`Sinkronisasi ${labelOf("ad_platform", platform)}: `
        + `${d.spend_inserted || 0} baris baru, ${d.spend_updated || 0} diperbarui.`);
      load();
    } catch (e) {
      // Mode simulasi menjawab 400 dengan alasan lengkap — tampilkan apa adanya supaya
      // pemakai tahu harus mengisi env yang mana, bukan sekadar "gagal".
      toast.error(e?.response?.data?.detail || "Sinkronisasi gagal.", { duration: 9000 });
    } finally { setSyncing(false); }
  };

  const totals = data?.totals || {};
  const series = data?.series || [];

  const columns = useMemo(() => [
    {
      key: "date", header: "Tanggal", sortable: true, width: "12%",
      render: (r) => <span className="text-sm tabular-nums">{r.date}</span>,
      exportValue: (r) => r.date,
    },
    {
      key: "campaign_name", header: "Kampanye", sortable: true, width: "24%",
      render: (r) => (
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{r.campaign_name}</p>
          <p className="text-xs text-muted-foreground">
            {labelOf("ad_platform", r.platform)}
            {r.adset_name || r.adset_id ? ` · ${r.adset_name || r.adset_id}` : ""}
            {r.ad_name || r.ad_id ? ` · ${r.ad_name || r.ad_id}` : ""}
          </p>
        </div>
      ),
      exportValue: (r) => r.campaign_name,
    },
    {
      key: "spend", header: "Biaya", sortable: true, align: "right",
      render: (r) => <MoneyText value={r.spend} />,
      // Baris ini SELALU punya nominal (itulah sebabnya barisnya ada); ekspor mengirim
      // angkanya apa adanya — tanpa `|| 0` yang bisa menyamarkan nilai kosong sebagai nol.
      exportValue: (r) => r.spend,
    },
    {
      key: "impressions", header: "Impresi", sortable: true, align: "right",
      render: (r) => (r.impressions === null || r.impressions === undefined
        ? <span className="text-xs text-muted-foreground">tidak dilaporkan</span>
        : <span className="text-sm tabular-nums">{formatNumber(r.impressions)}</span>),
      exportValue: (r) => r.impressions ?? "",
    },
    {
      key: "clicks", header: "Klik", sortable: true, align: "right",
      render: (r) => (r.clicks === null || r.clicks === undefined
        ? <span className="text-xs text-muted-foreground">—</span>
        : <span className="text-sm tabular-nums">{formatNumber(r.clicks)}</span>),
      exportValue: (r) => r.clicks ?? "",
    },
    {
      key: "leads_platform", header: "Lead (platform)", align: "right",
      render: (r) => (r.leads_platform === null || r.leads_platform === undefined
        ? <span className="text-xs text-muted-foreground">—</span>
        : <span className="text-sm tabular-nums">{formatNumber(r.leads_platform)}</span>),
      exportValue: (r) => r.leads_platform ?? "",
    },
    {
      key: "source", header: "Asal angka", sortable: true,
      render: (r) => <SourceLabels sources={[r.source]} />,
      exportValue: (r) => r.source,
    },
    {
      key: "revisions", header: "Koreksi", align: "right", hidden: true,
      render: (r) => (r.revisions ? (
        <span className="text-xs text-amber-700" title={`Terakhir oleh ${r.updated_by}`}>
          {r.revisions}× diperbaiki
        </span>
      ) : <span className="text-xs text-muted-foreground">—</span>),
      exportValue: (r) => r.revisions || 0,
    },
  ], [labelOf]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "platform", label: "Platform", type: "multiselect", options: options("ad_platform") },
      { key: "source", label: "Asal angka", type: "multiselect",
        options: options("ad_spend_source") },
      { key: "campaign_id", label: "Kampanye", type: "select",
        options: (data?.campaigns || []).map((c) => ({ value: c.id, label: c.name })) },
      { key: "range", label: "Rentang tanggal", type: "daterange",
        fromKey: "date_from", toKey: "date_to" },
    ]} />
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-3xl text-sm text-muted-foreground">
          Rentang aktif: <strong>{data?.range?.from || "…"} → {data?.range?.to || "…"}</strong>
          {" "}(bawaan 30 hari terakhir). Impor CSV yang sama dua kali TIDAK menambah biaya:
          barisnya dikenali dari kunci platform + kampanye + adset + iklan + tanggal.
        </p>
        <div className="flex flex-wrap gap-2">
          <div className="w-40">
            <ReferenceSelect group="ads_period" value={period} onChange={setPeriod}
              testId={ADS.spendPeriod} />
          </div>
          {canManage ? (
            <Button size="sm" variant="outline" data-testid={ADS.syncBtn} disabled={syncing}
              onClick={() => sync(query.platform?.[0] || "meta")}>
              <RefreshCw className={`mr-1.5 h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
              Tarik dari platform
            </Button>
          ) : null}
          {canCreate ? (
            <>
              <Button size="sm" variant="outline" data-testid={ADS.importBtn}
                onClick={() => setImportOpen(true)}>
                <Download className="mr-1.5 h-4 w-4" /> Impor CSV
              </Button>
              <Button size="sm" data-testid={ADS.spendAdd} onClick={() => setEntryOpen(true)}>
                <Plus className="mr-1.5 h-4 w-4" /> Entri Biaya
              </Button>
            </>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard label="Total biaya" value={<MoneyText value={totals.spend} short />} testId={`${P93.spendKpi}-spend`}
          hint={`${totals.rows || 0} baris · ${totals.days || 0} hari terisi`} onOpen={() => drill("spend", "Total biaya per kampanye")} />
        <KpiCard label="Impresi" value={formatNumber(totals.impressions || 0)} tone="sky" testId={`${P93.spendKpi}-impressions`}
          onOpen={() => drill("impressions", "Impresi per kampanye")} />
        <KpiCard label="Klik" value={formatNumber(totals.clicks || 0)} tone="sky" testId={`${P93.spendKpi}-clicks`}
          hint={totals.impressions
            ? `CTR ${((totals.clicks / totals.impressions) * 100).toFixed(2)}%` : "CTR —"}
          onOpen={() => drill("clicks", "Klik per kampanye")} />
        <KpiCard label="Lead menurut platform" value={formatNumber(totals.leads_platform || 0)} testId={`${P93.spendKpi}-leads_platform`}
          tone="amber" hint="dibandingkan lead nyata di tab Kinerja" onOpen={() => drill("leads_platform", "Lead menurut platform, per kampanye")} />
        <KpiCard label="Biaya per klik" testId={`${P93.spendKpi}-cpc`}
          value={totals.clicks ? formatIDR(Math.round(totals.spend / totals.clicks)) : "—"}
          hint={totals.clicks ? "total biaya ÷ total klik" : "klik belum dilaporkan"}
          onOpen={() => drill("clicks", "Biaya per klik — klik per kampanye (penyebut)")} />
      </div>
      <DrilldownDialog target={drillTarget} onOpenChange={(o) => { if (!o) setDrillTarget(null); }} />

      <ChartFrame testId={ADS.spendChart} title="Biaya iklan per periode"
        description={`Agregasi ${labelOf("ads_period", period)} dari baris biaya — `
          + `asal angka: ${(totals.sources || []).map((s) => labelOf("ad_spend_source", s))
            .join(", ") || "belum ada"}`}
        rows={series} loading={loading} error={error} onRetry={load}
        csvColumns={[{ key: "bucket", header: "Periode" }, { key: "spend", header: "Biaya" },
          { key: "impressions", header: "Impresi" }, { key: "clicks", header: "Klik" }]}
        csvName="biaya-iklan-per-periode" height={260}
        emptyText="Belum ada biaya iklan pada rentang ini — isi lewat Entri Biaya atau impor CSV.">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={series}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="bucket" fontSize={11} />
            <YAxis fontSize={11} tickFormatter={(v) => `${Math.round(v / 1000)}rb`} />
            <Tooltip formatter={(v) => formatIDR(v)} />
            <Bar dataKey="spend" name="Biaya" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>

      <DataTable testId={ADS.spendTable}
        testIds={{ row: ADS.spendRow, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="baris biaya" exportName="biaya-iklan" onRefresh={load}
        searchPlaceholder=""
        emptyTitle={activeCount ? "Tidak ada biaya yang cocok" : "Belum ada biaya iklan"}
        emptyDescription={activeCount
          ? "Longgarkan filter atau lebarkan rentang tanggalnya."
          : "Tanpa biaya iklan, CPL/CAC/ROAS tidak bisa dihitung — dan tidak akan pernah kami tampilkan sebagai 0."}
        emptyActionLabel={canCreate && !activeCount ? "Entri Biaya" : (activeCount ? "Reset filter" : "")}
        emptyAction={activeCount ? () => reset() : (canCreate ? () => setEntryOpen(true) : null)} />

      <SpendEntryDialog open={entryOpen} onOpenChange={setEntryOpen}
        campaigns={data?.campaigns || []} onDone={load} />
      <SpendImportDialog open={importOpen} onOpenChange={setImportOpen} onDone={load} />
    </div>
  );
}
