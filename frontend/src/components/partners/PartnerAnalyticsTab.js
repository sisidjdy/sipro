import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import KpiCard from "@/components/patterns/KpiCard";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { PARTNERS } from "@/constants/testIds";

/**
 * PartnerAnalyticsTab — analitik mitra (Fase 42 §7).
 *
 * Setiap kolom punya rumus yang tertulis di spec dan dihitung backend dari data nyata
 * (lead, agenda survey, deal, tagihan fee). Nama mitra & angka lead bisa DIKLIK ke daftar
 * lead terfilter, jadi setiap angka bisa ditelusuri sampai barisnya.
 */
export default function PartnerAnalyticsTab() {
  const { labelOf } = useReference();
  const [range, setRange] = useState({ created_from: "", created_to: "" });
  const [rows, setRows] = useState([]);
  const [totals, setTotals] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/partners/analytics", {
        params: {
          created_from: range.created_from || undefined,
          created_to: range.created_to || undefined,
        },
      });
      setRows(res.data.data || []);
      setTotals(res.data.totals || {});
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat analitik mitra.");
    } finally { setLoading(false); }
  }, [range]);

  useEffect(() => { load(); }, [load]);

  const kpis = useMemo(() => [
    { label: "Mitra aktif", value: `${totals.active_partners || 0}/${totals.partners || 0}`,
      hint: "boleh menyetor lead & menerima fee" },
    { label: "Lead dari mitra", value: totals.leads || 0,
      hint: `${totals.booked || 0} booking · ${totals.won || 0} closing` },
    { label: "Kontribusi pendapatan", value: <MoneyText value={totals.revenue} short />,
      hint: "nilai deal booking/selesai dari lead mitra" },
    { label: "Beban fee (disetujui)", value: <MoneyText value={totals.fee_expense} short />,
      hint: `sisa utang ${new Intl.NumberFormat("id-ID").format(totals.fee_outstanding || 0)}` },
    { label: "ROI mitra", value: totals.roi_pct === null || totals.roi_pct === undefined
      ? "—" : `${totals.roi_pct}%`, hint: "(pendapatan − fee) ÷ fee" },
    { label: "Biaya per closing", value: <MoneyText value={totals.cost_per_won} short />,
      hint: "Σ fee ÷ jumlah closing" },
    { label: "Fee menunggu persetujuan", value: <MoneyText value={totals.fee_waiting} short />,
      hint: "belum menjadi utang sampai disetujui" },
    { label: "Sengketa atribusi", value: totals.conflicts_pending || 0,
      hint: "lead diklaim lebih dari satu mitra",
      tone: totals.conflicts_pending ? "amber" : "primary" },
  ], [totals]);

  if (loading && !rows.length) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Kualitas mitra diukur dari bukti: lead yang benar-benar dihubungi, survey yang
          benar-benar dihadiri, closing yang benar-benar terjadi — lalu dibandingkan dengan
          fee yang dibayarkan.
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="paf" className="text-xs">Lead dari</Label>
            <Input id="paf" type="date" className="h-9" value={range.created_from}
              onChange={(e) => setRange((r) => ({ ...r, created_from: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="pat" className="text-xs">s/d</Label>
            <Input id="pat" type="date" className="h-9" value={range.created_to}
              onChange={(e) => setRange((r) => ({ ...r, created_to: e.target.value }))} />
          </div>
          <Button size="sm" variant="outline" onClick={load} aria-label="Muat ulang analitik">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => (
          <KpiCard key={k.label} label={k.label} value={k.value} hint={k.hint} tone={k.tone} />
        ))}
      </div>

      {rows.length === 0 ? (
        <EmptyState title="Belum ada data mitra"
          description="Analitik akan terisi setelah ada lead beratribusi mitra." />
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
          <table data-testid={PARTNERS.analyticsTable} className="w-full text-sm">
            <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Mitra</th>
                <th className="px-3 py-2 text-right">Lead</th>
                <th className="px-3 py-2 text-right">Dihubungi</th>
                <th className="px-3 py-2 text-right">Survey hadir</th>
                <th className="px-3 py-2 text-right">Booking</th>
                <th className="px-3 py-2 text-right">Closing</th>
                <th className="px-3 py-2 text-right">Win rate</th>
                <th className="px-3 py-2 text-right">Pendapatan</th>
                <th className="px-3 py-2 text-right">Beban fee</th>
                <th className="px-3 py-2 text-right">Sisa utang</th>
                <th className="px-3 py-2 text-right">Biaya/closing</th>
                <th className="px-3 py-2 text-right">ROI</th>
                <th className="px-3 py-2 text-right">Median hari closing</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.partner_id} data-testid={PARTNERS.analyticsRow}
                  data-partner={r.partner_id} className="border-t">
                  <td className="px-3 py-2">
                    <Link to={`/partners/${r.partner_id}`}
                      aria-label={`Buka profil mitra ${r.name}`}
                      className="font-medium text-primary hover:underline">
                      {r.name}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {labelOf("partner_kind", r.partner_kind)} · {r.status}
                    </p>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    <Link to={r.drill_leads} data-partner={r.partner_id}
                      aria-label={`Buka lead dari ${r.name}`} className="hover:underline">
                      {r.leads}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.contacted}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.survey_attended}
                    {r.qualified_pct !== null ? (
                      <span className="text-xs text-muted-foreground"> ({r.qualified_pct}%)</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.booked}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.won}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.win_rate_pct === null ? "—" : `${r.win_rate_pct}%`}
                  </td>
                  <td className="px-3 py-2 text-right"><MoneyText value={r.revenue} short /></td>
                  <td className="px-3 py-2 text-right">
                    <MoneyText value={r.fee_expense} short />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <MoneyText value={r.fee_outstanding} short
                      className={r.fee_outstanding ? "text-amber-700" : ""} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <MoneyText value={r.cost_per_won} short />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.roi_pct === null ? "—" : `${r.roi_pct}%`}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.median_days_to_won ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
