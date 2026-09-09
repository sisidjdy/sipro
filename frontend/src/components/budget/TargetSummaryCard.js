import React, { useEffect, useState } from "react";
import { Target } from "lucide-react";
import { Link } from "react-router-dom";

import MetricCard from "@/components/patterns/MetricCard";
import { Count, MissingNote, Pct } from "@/components/budget/parts";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * TargetSummaryCard — kartu ringkasan target di halaman detail proyek.
 *
 * Tanpa target AKTIF, kartu ini TIDAK menggambar “target 0 unit · tercapai 100%” (yang akan
 * membuat proyek tanpa rencana terlihat paling sukses). Ia menyebut bahwa targetnya belum ada
 * dan menautkan ke tempat membuatnya.
 */
export default function TargetSummaryCard({ projectId }) {
  const { labelOf } = useReference();
  const [data, setData] = useState(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    api.get(`/projects/${projectId}/target-summary`)
      .then((r) => setData(r.data.data))
      .catch((e) => { if (e?.response?.status === 403) setDenied(true); });
  }, [projectId]);

  if (denied || !data) return null;

  if (data.state === "kosong") {
    return (
      <div data-testid={BUDGET.projectTargetCard} data-state="kosong"
        className="rounded-xl border border-dashed bg-card/60 p-4">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Target className="h-4 w-4 text-primary" /> Target penjualan proyek
        </p>
        <MissingNote items={data.missing} title="Belum bisa ditampilkan karena:" />
        <Link to={data.drill}
          className="mt-2 inline-block rounded-md border bg-card px-3 py-1.5 text-xs font-medium shadow-[var(--shadow-card)]">
          Buat target di RAB/BoQ → Target &amp; Budget
        </Link>
      </div>
    );
  }

  const t = data.totals || {};
  const cur = data.current_period;
  return (
    <div data-testid={BUDGET.projectTargetCard} data-state={data.state}
      className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Target className="h-4 w-4 text-primary" /> {data.target?.name}
          <span className="text-[11px] font-normal text-muted-foreground">
            {labelOf("target_method", data.target?.method)} ·{" "}
            {data.target?.horizon?.start} s/d {data.target?.horizon?.end}
          </span>
        </p>
        <Link to={data.drill} className="text-xs font-medium text-primary">
          Lihat rencana bulanan →
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard compact label="Target unit" value={t.unit_target} tone="primary" />
        <MetricCard compact label="Realisasi unit" value={t.unit_actual_total} tone="emerald"
          hint={data.achievement_pct !== null ? `${data.achievement_pct}% tercapai`
            : "pencapaian belum bisa dihitung"} />
        <MetricCard compact label="Target pendapatan" value={t.revenue_target} format="idr"
          tone="indigo" />
        <MetricCard compact label="Realisasi pendapatan" value={t.revenue_actual_total}
          format="idr" tone="sky"
          hint={data.revenue_achievement_pct !== null
            ? `${data.revenue_achievement_pct}% tercapai` : "pencapaian belum bisa dihitung"} />
      </div>
      {cur ? (
        <p className="rounded-lg border bg-secondary/40 p-2.5 text-[12px]">
          Bulan berjalan <span className="font-mono">{cur.period}</span>: rencana{" "}
          <Count value={cur.unit_plan} suffix="unit" /> · realisasi{" "}
          <Count value={cur.unit_actual} suffix="unit" /> · pencapaian{" "}
          <Pct value={cur.achievement_pct} />
          {cur.carry_over
            ? ` — termasuk ${cur.carry_over} unit kekurangan bulan sebelumnya`
            : ""}
        </p>
      ) : null}
      {data.projection ? (
        <p className="text-[11px] text-muted-foreground">
          Proyeksi habis terjual: {data.projection.sold_out_period || "sudah tercapai"}
          {data.projection.beyond_horizon ? " (melewati horizon target)" : ""}
        </p>
      ) : null}
      <MissingNote items={data.missing} title="Catatan kelengkapan:" />
    </div>
  );
}
