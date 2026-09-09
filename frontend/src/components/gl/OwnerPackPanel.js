import React, { useCallback, useEffect, useState } from "react";
import { FileBarChart, RefreshCw, Info, Lock, Unlock, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateTimeWIB } from "@/utils/formatters";
import { monthLabel } from "@/components/gl/ClosingChecklistPanel";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const thisMonth = () => new Date().toISOString().slice(0, 7);
const MISSING_TEXT = {
  laba_rugi: "Laba rugi", arus_kas: "Arus kas", laba_per_proyek: "Laba per proyek",
  arus_kas_per_proyek: "Arus kas per proyek",
};

function Section({ title, hint, children, testValue }) {
  return (
    <div data-testid={P49.ownerPackSection} data-section={testValue}
      className="space-y-2 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div>
        <p className="font-heading text-sm font-semibold">{title}</p>
        {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
      </div>
      {children}
    </div>
  );
}

function Line({ label, value, strong, tone }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed py-1 last:border-0">
      <span className={`text-xs ${strong ? "font-semibold" : "text-muted-foreground"}`}>{label}</span>
      <span className={`tabular-nums text-sm ${strong ? "font-semibold" : ""} ${tone || ""}`}>
        {value}
      </span>
    </div>
  );
}

/**
 * Paket Laporan Bulanan Owner (Fase 49D) — satu jawaban, bukan enam layar.
 *
 * Yang membuat paket ini bisa dipercaya: status penutupan periode ikut dibawa (siapa menutup,
 * kapan, diterobos atau tidak), bagian yang memang belum ada datanya dinyatakan sebagai
 * “belum ada data” — BUKAN Rp 0 — dan laporan dari periode yang masih terbuka diberi
 * peringatan bahwa angkanya masih bisa berubah.
 */
export default function OwnerPackPanel() {
  const [period, setPeriod] = useState(thisMonth());
  const [pack, setPack] = useState(null);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (p) => {
    setLoading(true); setError("");
    try {
      const [pk, hist] = await Promise.all([
        api.get("/gl/reports/owner-pack", { params: { period: p } }),
        api.get("/gl/reports/closing-history", { params: { limit: 12 } }),
      ]);
      setPack(pk.data.data || null);
      setHistory(hist.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat paket laporan owner.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(period); }, [load, period]);

  if (loading) return <LoadingCards count={5} />;
  if (error) return <ErrorState message={error} onRetry={() => load(period)} />;

  const pl = pack?.income_statement || {};
  const bs = pack?.balance_sheet || {};
  const cf = pack?.cash_flow || {};
  const proj = pack?.project_pl || {};
  const pcf = pack?.project_cash_flow || {};
  const closed = pack?.status === "closed";
  const missing = pack?.missing || [];

  return (
    <div data-testid={P49.ownerPackPanel} className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="p49-ownerpack-month">Masa laporan (bulan)</Label>
          <Input id="p49-ownerpack-month" type="month" className="w-[170px]"
            data-testid={P49.ownerPackPeriod} value={period}
            onChange={(e) => setPeriod(e.target.value || thisMonth())} />
        </div>
        <div className="flex items-center gap-2">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <FileBarChart className="h-4 w-4 text-primary" /> Posisi per {pack?.as_of || "-"}
          </p>
          <Button size="icon" variant="outline" data-testid={P49.ownerPackRefresh}
            aria-label="Muat ulang paket laporan" title="Muat ulang" onClick={() => load(period)}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div data-testid={P49.ownerPackTrust} data-status={pack?.status}
        className={`flex flex-wrap items-start gap-2 rounded-xl border p-3.5 text-sm ${closed
          ? "border-slate-200 bg-slate-50 text-slate-800"
          : "border-amber-200 bg-amber-50 text-amber-900"}`}>
        {closed ? <Lock className="mt-0.5 h-4 w-4 shrink-0" /> : <Unlock className="mt-0.5 h-4 w-4 shrink-0" />}
        <div className="min-w-0 space-y-1">
          <p className="font-medium">{pack?.trust_note}</p>
          {closed && pack?.closed_by ? (
            <p className="text-xs">
              Ditutup oleh {pack.closed_by} · {formatDateTimeWIB(pack.closed_at)}
            </p>
          ) : null}
          {pack?.override_reason ? (
            <p className="text-xs font-medium">
              DITEROBOS oleh {pack.override_by}: “{pack.override_reason}”
              {pack.override_items?.length ? ` (${pack.override_items.join(", ")})` : ""}
            </p>
          ) : null}
          <p className="text-xs">
            Tutup tahun {pack?.year_closing?.year}: {" "}
            <StatusPill status={pack?.year_closing?.state} group="year_closing_state"
              tone={pack?.year_closing?.state === "closed" ? "closed" : "open"} />
            {pack?.year_closing?.entry_no ? ` · jurnal ${pack.year_closing.entry_no}` : ""}
          </p>
        </div>
      </div>

      {missing.length ? (
        <div data-testid={P49.ownerPackMissing}
          className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 p-3.5 text-sm text-sky-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Bagian yang BELUM ADA DATANYA (bukan Rp 0):</p>
            <p className="text-xs">
              {missing.map((m) => MISSING_TEXT[m] || m).join(", ")} — {pack?.detail}
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <MetricCard label="Laba (rugi) bulan ini" value={pl.net_income} format="idr"
          tone={(pl.net_income || 0) >= 0 ? "emerald" : "rose"} />
        <MetricCard label="Pendapatan" value={pl.total_revenue} format="idr" tone="primary" />
        <MetricCard label="Total aset" value={bs.total_assets} format="idr" tone="sky" />
        <MetricCard label="Ekuitas" value={bs.total_equity} format="idr" tone="violet" />
        <MetricCard label="Perubahan kas" value={cf.net_change} format="idr"
          tone={(cf.net_change || 0) >= 0 ? "emerald" : "rose"} />
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Section title="Laba Rugi" testValue="laba_rugi"
          hint={`Pertumbuhan pendapatan ${pl.growth?.revenue_pct ?? "-"}% · marjin bersih ${pl.net_margin_pct ?? 0}%`}>
          <Line label="Pendapatan" value={formatIDR(pl.total_revenue)} />
          <Line label="Beban pokok" value={formatIDR(pl.total_cogs)} />
          <Line label="Laba kotor" value={formatIDR(pl.gross_profit)} />
          <Line label="Beban usaha" value={formatIDR(pl.total_opex)} />
          <Line label="Laba (rugi) bersih" value={formatIDR(pl.net_income)} strong
            tone={(pl.net_income || 0) >= 0 ? "text-emerald-700" : "text-rose-700"} />
        </Section>

        <Section title="Neraca" testValue="neraca"
          hint={bs.balanced ? "Aset = Liabilitas + Ekuitas (seimbang)" : "TIDAK SEIMBANG — laporkan ke admin"}>
          <Line label="Aset lancar" value={formatIDR(bs.current_assets)} />
          <Line label="Aset tidak lancar" value={formatIDR(bs.noncurrent_assets)} />
          <Line label="Total aset" value={formatIDR(bs.total_assets)} strong />
          <Line label="Liabilitas" value={formatIDR(bs.total_liabilities)} />
          <Line label="Ekuitas + laba periode" value={formatIDR((bs.total_equity || 0) + (bs.net_income || 0))} strong />
        </Section>

        <Section title="Arus Kas" testValue="arus_kas"
          hint={cf.reconciled ? "Cocok dengan mutasi akun kas" : "Belum cocok dengan mutasi akun kas"}>
          <Line label="Kas awal" value={formatIDR(cf.opening_cash)} />
          <Line label="Operasi" value={formatIDR(cf.operating?.total)} />
          <Line label="Investasi" value={formatIDR(cf.investing?.total)} />
          <Line label="Pendanaan" value={formatIDR(cf.financing?.total)} />
          <Line label="Kas akhir" value={formatIDR(cf.closing_cash)} strong />
        </Section>
      </div>

      <Section title="Laba per Proyek" testValue="laba_per_proyek"
        hint="Baris “tidak teralokasi” ditampilkan apa adanya — tidak dibagi rata ke proyek.">
        {!(proj.rows || []).length ? (
          <p className="text-xs text-muted-foreground">Belum ada data laba per proyek pada masa ini.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Proyek</TableHead>
                <TableHead className="text-right">Pendapatan</TableHead>
                <TableHead className="text-right">Beban pokok</TableHead>
                <TableHead className="text-right">Beban usaha</TableHead>
                <TableHead className="text-right">WIP/capex</TableHead>
                <TableHead className="text-right">Laba (rugi)</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {(proj.rows || []).map((r, i) => (
                  <TableRow key={r.project_id || `unalloc_${i}`} data-testid={P49.ownerPackProjectRow}
                    data-project={r.project_id || "unallocated"}
                    className={r.project_id ? "" : "bg-amber-50/60"}>
                    <TableCell className="text-sm font-medium">{r.project_name}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.revenue)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.cogs)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.opex)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.capex_wip)}</TableCell>
                    <TableCell className={`text-right tabular-nums text-sm font-semibold ${(r.net_income || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                      {formatIDR(r.net_income)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <p className="text-[11px] text-muted-foreground">
          Arus kas per proyek masa ini: {pcf.tie_out?.matches ? "tie-out cocok" : "tie-out SELISIH"}
          {" "}(Σ proyek {formatIDR(pcf.tie_out?.sum_projects)} vs konsolidasi {formatIDR(pcf.tie_out?.consolidated_net_change)}).
        </p>
      </Section>

      <Section title="Analisa Rasio" testValue="rasio"
        hint={`Sehat ${pack?.ratios?.counts?.healthy || 0} · perhatian ${pack?.ratios?.counts?.watch || 0} · risiko ${pack?.ratios?.counts?.risk || 0}`}>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {(pack?.ratios?.groups || []).map((g) => (
            <div key={g.key} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-xs font-semibold">{g.label}</p>
              {(g.items || []).map((it) => (
                <div key={it.name} data-testid={P49.ownerPackRatio}
                  className="mt-1 flex items-baseline justify-between gap-2">
                  <span className="text-[11px] text-muted-foreground">{it.name}</span>
                  <span className="tabular-nums text-xs font-medium">
                    {it.value === null || it.value === undefined ? "belum ada data" : `${it.value}${it.unit || ""}`}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Section>

      <Section title="Riwayat Penutupan" testValue="riwayat"
        hint="Bulan yang ditutup dengan terobosan ditandai agar tidak lewat dari perhatian direksi.">
        {!(history?.periods || []).length ? (
          <p className="text-xs text-muted-foreground">Belum ada periode yang pernah ditutup.</p>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Periode</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Ditutup oleh</TableHead>
                <TableHead>Terobosan</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {(history.periods || []).map((r) => (
                  <TableRow key={r.period} data-testid={P49.closingHistoryRow} data-period={r.period}
                    data-overridden={String(!!r.override_by)}>
                    <TableCell className="text-sm font-medium">{monthLabel(r.period)}</TableCell>
                    <TableCell>
                      <StatusPill status={r.status === "closed" ? "closed" : "open"}
                        label={r.status === "closed" ? "Ditutup" : "Terbuka"} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.closed_by || "-"}
                      {r.closed_at ? ` · ${formatDateTimeWIB(r.closed_at)}` : ""}
                    </TableCell>
                    <TableCell className="max-w-[380px] text-xs">
                      {r.override_by ? (
                        <span className="font-medium text-amber-800">
                          <History className="mr-1 inline h-3 w-3" />
                          {r.override_by}: “{r.override_reason}”
                        </span>
                      ) : <span className="text-muted-foreground">—</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
    </div>
  );
}
