import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, RefreshCw, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import EmptyState from "@/components/patterns/EmptyState";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import WarrantyClaimList from "@/components/handover/WarrantyClaimList";
import { ClaimActionDialog } from "@/components/handover/WarrantyClaimDialogs";
import api from "@/services/apiClient";
import { formatDateWIB } from "@/utils/formatters";
import { P50 } from "@/constants/testIds";

function Kpi({ label, value, hint, testId }) {
  return (
    <div data-testid={testId} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 font-heading text-xl font-semibold tabular-nums">{value}</p>
      {hint ? <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/**
 * Papan garansi & klaim seluruh proyek (Fase 50A).
 *
 * Dipasang sebagai TAB di halaman Progres & Mutu Konstruksi — bukan pintu sidebar baru —
 * karena pekerjaan garansi dikerjakan orang yang sama dengan pekerjaan pembangunan.
 *
 * Rekapnya menolak berbohong: kalau belum ada klaim yang ditutup, rata-rata hari
 * penyelesaian ditulis “belum ada datanya”, bukan 0 hari; dan badge tie-out membuktikan
 * jumlah per status benar-benar sama dengan jumlah klaim.
 */
export default function WarrantyBoardPanel({ projectId }) {
  const [board, setBoard] = useState([]);
  const [claims, setClaims] = useState([]);
  const [report, setReport] = useState(null);
  const [state, setState] = useState("");
  const [category, setCategory] = useState("");
  const [period, setPeriod] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { project_id: projectId || undefined };
      const [b, c, r] = await Promise.all([
        api.get("/handover/warranty/board", { params }),
        api.get("/handover/claims", { params: { ...params, state: state || undefined,
          category: category || undefined } }),
        api.get("/handover/claims/report", { params: { ...params,
          period: period || undefined } }),
      ]);
      setBoard(b.data.data || []);
      setClaims(c.data.data || []);
      setReport(r.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat papan garansi.");
    } finally { setLoading(false); }
  }, [projectId, state, category, period]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const tie = report?.tie_out || {};

  return (
    <div data-testid={P50.boardPanel} className="space-y-5">
      <div data-testid={P50.reportCard} className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-1.5 font-heading text-lg font-semibold">
              <ShieldCheck className="h-4 w-4 text-primary" /> Garansi &amp; klaim pasca-huni
            </h3>
            <p className="text-sm text-muted-foreground">{report?.detail}</p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="p50-period" className="text-[11px]">Bulan pengajuan</Label>
              <Input id="p50-period" type="month" className="w-36"
                data-testid={P50.reportPeriod} value={period}
                onChange={(e) => setPeriod(e.target.value)} />
            </div>
            <Button size="sm" variant="outline" onClick={load}>
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Muat ulang
            </Button>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi label="Klaim tercatat" value={report?.total ?? 0}
            hint={`${report?.open ?? 0} masih berjalan`} />
          <Kpi label="Rumah dipantau" value={board.length}
            hint="sudah diserahterimakan" />
          <Kpi label="Rata-rata hari selesai"
            value={report?.avg_days_to_close ?? "—"}
            hint={report?.avg_days_note || "dari klaim yang sudah ditutup"} />
          <div data-testid={P50.reportTieOut}
            className={`rounded-xl border p-3 text-[12px] ${tie.matches
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : "border-rose-200 bg-rose-50 text-rose-900"}`}>
            <p className="font-semibold">
              {tie.matches ? "Tie-out cocok" : "Tie-out TIDAK cocok"}
            </p>
            <p className="mt-0.5">{tie.detail}</p>
            <p className="mt-0.5 tabular-nums">
              Σ per status {tie.sum_per_state ?? 0} = total {tie.total ?? 0}
            </p>
          </div>
        </div>

        {report?.missing ? (
          <p data-testid={P50.reportMissing}
            className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-[13px] text-slate-700">
            {report.detail}
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(report?.per_state || {}).map(([k, v]) => (
              <span key={k}
                className="rounded-full border bg-card px-2 py-0.5 text-[11px] text-muted-foreground shadow-[var(--shadow-card)]">
                {k}: <span className="font-semibold text-foreground tabular-nums">{v}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2">
        <h4 className="section-title">Rumah dalam masa garansi</h4>
        {!board.length ? (
          <div data-testid={P50.boardEmpty}>
            <EmptyState icon={ShieldCheck} title="Belum ada rumah yang diserahterimakan"
              description="Papan ini terisi begitu BAST serah terima diterbitkan dari tab Serah Terima & Garansi di halaman unit." />
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full text-[13px]">
              <thead className="bg-secondary/60 text-left text-[12px] text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Rumah</th>
                  <th className="px-3 py-2">BAST</th>
                  <th className="px-3 py-2">Diserahkan</th>
                  <th className="px-3 py-2">Pembeli</th>
                  <th className="px-3 py-2">Garansi</th>
                  <th className="px-3 py-2">Klaim</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {board.map((r) => (
                  <tr key={r.handover_id} data-testid={P50.boardRow} className="border-t">
                    <td className="px-3 py-2 font-medium">{r.unit_code}</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.number}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {formatDateWIB(r.handed_over_at)}
                    </td>
                    <td className="px-3 py-2">{r.buyer_name || "—"}</td>
                    <td className="px-3 py-2">
                      <span className="text-emerald-700">{r.aktif} aktif</span>
                      {r.hampir_habis ? (
                        <span className="text-amber-700"> · {r.hampir_habis} hampir habis</span>
                      ) : null}
                      {r.habis ? (
                        <span className="text-muted-foreground"> · {r.habis} habis</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 tabular-nums">
                      {r.claims_total}
                      {r.claims_open ? (
                        <span className="text-amber-700"> ({r.claims_open} berjalan)</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <Link to={`/units/${r.unit_id}?tab=handover`}
                        className="inline-flex items-center gap-1 text-[12px] font-medium text-primary hover:underline">
                        Buka rumah <ExternalLink className="h-3 w-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div data-testid={P50.claimsPanel} className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h4 className="section-title">Daftar kerja klaim garansi</h4>
          <div className="flex flex-wrap items-end gap-2">
            <div className="w-48 space-y-1">
              <Label className="text-[11px]">Status</Label>
              <ReferenceSelect group="warranty_claim_state" value={state} onChange={setState}
                allowEmpty emptyLabel="Semua status" testId={P50.claimsStateFilter} />
            </div>
            <div className="w-56 space-y-1">
              <Label className="text-[11px]">Bagian</Label>
              <ReferenceSelect group="warranty_category" value={category}
                onChange={setCategory} allowEmpty emptyLabel="Semua bagian"
                testId={P50.claimsCategoryFilter} />
            </div>
          </div>
        </div>
        <WarrantyClaimList claims={claims}
          onAction={(mode, claim) => setAction({ mode, claim })}
          emptyHint="Tidak ada klaim yang cocok dengan saringan ini." />
      </div>

      <ClaimActionDialog mode={action?.mode} claim={action?.claim} open={!!action}
        onOpenChange={(v) => !v && setAction(null)} onDone={load} />
    </div>
  );
}
