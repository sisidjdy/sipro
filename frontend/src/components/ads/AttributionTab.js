import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import KpiCard from "@/components/patterns/KpiCard";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";
import MoneyText from "@/components/patterns/MoneyText";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { CostMetric } from "@/components/ads/CostStatus";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR, formatNumber } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ADS, DT, P93 } from "@/constants/testIds";

/**
 * AttributionTab — funnel atribusi bertingkat: kampanye → ad set → iklan → creative.
 *
 * Dua hal yang membuat layar ini berbeda dari tab “Atribusi” lama di Automasi & Channel
 * (yang kini DIHAPUS supaya satu urusan punya satu pintu):
 *  1. **Biaya ikut masuk** — jadi CPL per kampanye bisa dilihat di tempat yang sama dengan
 *     jumlah leadnya. Untuk tingkat ad set/iklan, biaya SENGAJA dikosongkan dengan alasan
 *     tertulis: membagi biaya kampanye secara rata ke ad set adalah karangan.
 *  2. **Campuran kanal** (iklan berbayar vs mitra vs organik) — pertanyaan pertama pemilik
 *     setiap bulan: “yang closing itu datang dari iklan, mitra, atau datang sendiri?”
 */
export default function AttributionTab() {
  const { labelOf } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { date_from: "", date_to: "" }, sort: "", direction: "desc", limit: 50,
  });
  const [level, setLevel] = useState("campaign");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [drillTarget, setDrillTarget] = useState(null);
  const drill = (sub, label) => setDrillTarget({ key: `ads:${sub}`, label, params: {
    ctx: "attribution", date_from: data?.range?.from, date_to: data?.range?.to } });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/ads/attribution", { params: { ...apiParams, level } });
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat atribusi.");
    } finally { setLoading(false); }
  }, [apiParams, level]);

  useEffect(() => { load(); }, [load]);

  const t = data?.totals || {};
  const rows = data?.rows || [];
  const mix = data?.channel_mix || [];

  const columns = useMemo(() => [
    {
      key: "source", header: "Sumber", width: "14%",
      render: (r) => <span className="text-sm font-medium">{r.source_label}</span>,
      exportValue: (r) => r.source_label,
    },
    {
      key: "campaign", header: "Kampanye", width: "22%",
      render: (r) => (
        <div className="min-w-0">
          <Link to={`/leads?q=${encodeURIComponent(r.campaign)}`}
            className="truncate text-sm font-medium text-primary hover:underline">
            {r.campaign}
          </Link>
          <p className="text-xs text-muted-foreground">
            {r.campaign_known ? "terdaftar" : "belum terdaftar sebagai kampanye"}
            {level !== "campaign" ? ` · ${r.level_label}` : ""}
          </p>
        </div>
      ),
      exportValue: (r) => r.campaign,
    },
    {
      key: "channel_group", header: "Kanal",
      render: (r) => (
        <span className="rounded border bg-secondary px-1.5 py-0.5 text-xs">
          {labelOf("ads_channel_group", r.channel_group)}
        </span>
      ),
      exportValue: (r) => r.channel_group,
    },
    {
      key: "leads", header: "Lead", align: "right",
      render: (r) => <span className="text-sm tabular-nums">{formatNumber(r.leads)}</span>,
      exportValue: (r) => r.leads,
    },
    {
      key: "hot", header: "Hot", align: "right", hidden: true,
      render: (r) => <span className="text-sm tabular-nums">{formatNumber(r.hot)}</span>,
      exportValue: (r) => r.hot,
    },
    {
      key: "qualified", header: "Terkualifikasi", align: "right",
      render: (r) => <span className="text-sm tabular-nums">{formatNumber(r.qualified)}</span>,
      exportValue: (r) => r.qualified,
    },
    {
      key: "booked", header: "Booking", align: "right",
      render: (r) => (
        <div className="text-right">
          <span className="text-sm tabular-nums">{formatNumber(r.booked)}</span>
          <p className="text-xs text-muted-foreground">{r.conversion_pct}%</p>
        </div>
      ),
      exportValue: (r) => r.booked,
    },
    {
      key: "revenue", header: "Pendapatan", align: "right",
      render: (r) => <MoneyText value={r.revenue} short />,
      exportValue: (r) => r.revenue || 0,
    },
    {
      key: "spend", header: "Biaya kampanye", align: "right",
      render: (r) => (r.spend === null || r.spend === undefined ? (
        <span title={r.spend_note || ""} className="text-xs italic text-muted-foreground">
          {r.spend_note || "belum ada"}
        </span>
      ) : (
        <span title="Biaya seluruh kampanye (bukan alokasi per sumber) — kampanye yang sama di beberapa baris memakai angka yang sama">
          <MoneyText value={r.spend} short />
        </span>
      )),
      exportValue: (r) => r.spend ?? "",
    },
    {
      key: "cpl", header: "CPL", align: "right",
      render: (r) => <CostMetric value={r.cpl} render={(v) => formatIDR(v)}
        note={r.spend_note || ""} />,
      exportValue: (r) => r.cpl ?? "",
    },
    {
      key: "conversions", header: "Event CAPI", align: "right",
      render: (r) => <span className="text-sm tabular-nums text-amber-700">
        {formatNumber(r.conversions || 0)}
      </span>,
      exportValue: (r) => r.conversions || 0,
    },
  ], [labelOf, level]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "range", label: "Rentang tanggal", type: "daterange",
        fromKey: "date_from", toKey: "date_to" },
    ]} />
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Rentang: <strong>{data?.range?.from || "…"} → {data?.range?.to || "…"}</strong>
          {" "}(bawaan 90 hari). Naik-turunkan tingkat untuk melihat sampai ad set / iklan /
          materi — lead lama yang tidak membawa ID tingkat itu dikelompokkan sebagai
          “(tanpa ID)”, bukan disembunyikan.
        </p>
        <div className="w-56">
          <ReferenceSelect group="ads_attribution_level" value={level} onChange={setLevel}
            testId={ADS.attrLevel} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard label="Lead" value={formatNumber(t.leads || 0)} to="/leads" testId={`${P93.attrKpi}-leads`}
          drillLabel="Buka pipeline" onOpen={() => drill("leads", "Semua lead dalam rentang atribusi")} />
        <KpiCard label="Terkualifikasi" value={formatNumber(t.qualified || 0)} tone="amber" testId={`${P93.attrKpi}-qualified`}
          onOpen={() => drill("qualified", "Lead terkualifikasi")} />
        <KpiCard label="Booking" value={formatNumber(t.booked || 0)} tone="emerald" testId={`${P93.attrKpi}-booked`}
          onOpen={() => drill("booked", "Lead yang booking")} />
        <KpiCard label="Biaya iklan terpetakan" value={<MoneyText value={t.spend} short />} testId={`${P93.attrKpi}-spend`}
          hint="hanya kampanye yang terdaftar" onOpen={() => drill("spend", "Biaya iklan terpetakan per kampanye")} />
        <KpiCard label="CPL gabungan" value={t.cpl ? formatIDR(t.cpl) : "belum lengkap"} testId={`${P93.attrKpi}-cpl`}
          tone="sky" hint={t.cpl ? "biaya ÷ lead" : "data biaya belum lengkap"}
          onOpen={() => drill("spend", "CPL gabungan — biaya per kampanye (pembilang)")} />
      </div>
      <DrilldownDialog target={drillTarget} onOpenChange={(o) => { if (!o) setDrillTarget(null); }} />

      <div data-testid={ADS.channelMix} className="grid gap-3 sm:grid-cols-3">
        {mix.map((m) => (
          <div key={m.channel_group} data-channel={m.channel_group}
            className="rounded-lg border bg-card p-3.5 shadow-[var(--shadow-card)]">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {m.label}
            </p>
            <p className="mt-1 font-heading text-xl font-semibold tabular-nums">
              {formatNumber(m.leads)} <span className="text-sm font-normal">lead</span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {formatNumber(m.booked)} booking
              {m.booking_rate !== null ? ` (${m.booking_rate}%)` : ""} · pendapatan{" "}
              <MoneyText value={m.revenue} short />
            </p>
            <p className="text-xs text-muted-foreground">
              CPL {m.cpl ? formatIDR(m.cpl) : "— (tanpa biaya iklan)"}
            </p>
          </div>
        ))}
      </div>

      <DataTable testId={ADS.attrTable}
        testIds={{ row: ADS.attrRow, pagination: DT.pagination }}
        columns={columns} rows={rows} total={rows.length}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="baris atribusi" exportName="atribusi-lead" onRefresh={load}
        searchPlaceholder=""
        emptyTitle={activeCount ? "Tidak ada data pada rentang itu" : "Belum ada lead"}
        emptyDescription={activeCount
          ? "Lebarkan rentang tanggalnya."
          : "Atribusi muncul begitu lead masuk dari kanal apa pun (iklan, mitra, walk-in)."}
        emptyActionLabel={activeCount ? "Reset filter" : ""}
        emptyAction={activeCount ? () => reset() : null} />
    </div>
  );
}
