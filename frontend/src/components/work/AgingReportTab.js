import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, RefreshCw, SlidersHorizontal, Timer } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import KpiCard from "@/components/patterns/KpiCard";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatHours } from "@/utils/agingFilter";
import { fromNow } from "@/utils/formatters";
import api from "@/services/apiClient";
import { AGINGREPORT } from "@/constants/testIds";

/**
 * AgingReportTab — **Umur Tahap & SLA** (Fase 41).
 *
 * Pertanyaan yang sebelumnya TIDAK BISA dijawab aplikasi ini: "objek mana yang menganggur
 * paling lama di tahapnya, dan berapa yang sudah lewat SLA?". Umur tahap dulu diturunkan
 * ulang di setiap request dari `stage_history`, jadi tidak bisa difilter maupun diagregasi.
 *
 * Semua angka di sini datang dari agregasi database atas field tersimpan
 * (`stage_entered_at`/`stage_due_at`), dan setiap angka bisa DIKLIK ke daftar yang persis
 * dihitung (tautan `drill` dibentuk backend, bukan dikarang ulang di layar ini).
 */
export default function AgingReportTab() {
  const { can } = useAuth();
  const { labelOf } = useReference();
  // Izin diambil dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis
  // ulang di layar. Matriks RBAC bisa diubah admin lewat Pusat Konfigurasi; daftar peran
  // hardcode membuat tombol berbeda dengan jawaban server — tombol mati (403) atau
  // tombol yang seharusnya ada tapi hilang.
  const isAdmin = can("aging", "manage");
  const [entity, setEntity] = useState("lead");
  const [entities, setEntities] = useState([]);
  const [report, setReport] = useState(null);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [pol, rep, ovw] = await Promise.all([
        api.get("/aging/policy"),
        api.get("/aging/report", { params: { entity } }),
        api.get("/aging/overview"),
      ]);
      setEntities(pol.data.entities || []);
      setReport(rep.data.data);
      setOverview(ovw.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat laporan umur tahap.");
    } finally { setLoading(false); }
  }, [entity]);

  useEffect(() => { load(); }, [load]);

  const reconcile = async () => {
    setBusy(true);
    try {
      const res = await api.post("/aging/reconcile");
      const total = Object.values(res.data.data || {})
        .reduce((n, v) => n + (v.filled || 0) + (v.resynced || 0), 0);
      toast.success(total
        ? `Jam tahap disamakan & kebijakan SLA terbaru diberlakukan pada ${total} baris.`
        : "Jam tahap sudah sesuai — tidak ada yang perlu diubah.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyamakan jam tahap.");
    } finally { setBusy(false); }
  };

  const totals = report?.totals || {};
  const kpis = useMemo(() => [
    { label: "Total baris", value: totals.count || 0, hint: report?.label,
      drill: report?.rows?.length ? report.rows[0].drill?.split("?")[0] : null },
    { label: "Lewat SLA tahap", value: totals.over_sla || 0, tone: "amber",
      hint: "melewati ambang Pusat Konfigurasi", drill: totals.drill_over },
    { label: "Lewat 2× SLA", value: totals.over2_sla || 0, tone: "rose",
      hint: "perlu eskalasi supervisor", drill: totals.drill_over },
    { label: "Jam tahap turunan", value: totals.clock_derived || 0,
      hint: "baris lama yang belum punya jam tahap tersimpan" },
  ], [totals, report]);

  if (loading && !report) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={AGINGREPORT.tab} className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-heading text-lg font-semibold">Umur Tahap &amp; SLA</h2>
          <p className="text-sm text-muted-foreground">
            Berapa lama objek menganggur di tahapnya, dan mana yang sudah lewat janji waktu.
            Ambang SLA berasal dari Pusat Konfigurasi ({report?.sla_key}) — bukan angka mati
            di layar.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={entity} onValueChange={setEntity}>
            <SelectTrigger data-testid={AGINGREPORT.entitySelect} className="w-52"
              aria-label="Pilih objek umur tahap">
              <SelectValue placeholder="Pilih objek" />
            </SelectTrigger>
            <SelectContent>
              {entities.map((e) => (
                <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {isAdmin ? (
            <>
              <Button data-testid={AGINGREPORT.reconcile} size="sm" variant="outline"
                onClick={reconcile} disabled={busy}>
                <Timer className="mr-1.5 h-4 w-4" />
                {busy ? "Menyamakan…" : "Samakan jam tahap"}
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link data-testid={AGINGREPORT.policyLink} to="/config?group=sla">
                  <SlidersHorizontal className="mr-1.5 h-4 w-4" /> Ubah SLA
                </Link>
              </Button>
            </>
          ) : null}
          <Button data-testid={AGINGREPORT.refresh} size="sm" variant="outline"
            onClick={load} aria-label="Muat ulang laporan">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => (
          <KpiCard key={k.label} testId={AGINGREPORT.kpi} label={k.label} value={k.value}
            hint={k.hint} tone={k.tone} to={k.drill || undefined} />
        ))}
      </div>

      <div className="rounded-lg border bg-card shadow-[var(--shadow-card)]">
        <div className="border-b px-4 py-3">
          <h3 className="text-sm font-semibold">Per tahap · {report?.label}</h3>
          <p data-testid={AGINGREPORT.policy} className="text-xs text-muted-foreground">
            Umur tahap dihitung dari field tersimpan <code>stage_entered_at</code>; kolom SLA
            adalah ambang efektif tahap itu. Klik angka untuk membuka daftarnya.
          </p>
        </div>
        {(report?.rows || []).length === 0 ? (
          <div className="p-4">
            <EmptyState icon={Timer} title="Belum ada data pada objek ini"
              description="Belum ada baris yang bisa dihitung umur tahapnya." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table data-testid={AGINGREPORT.table} className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 text-left">Tahap</th>
                  <th className="px-4 py-2 text-right">SLA</th>
                  <th className="px-4 py-2 text-right">Jumlah</th>
                  <th className="px-4 py-2 text-right">Lewat SLA</th>
                  <th className="px-4 py-2 text-right">Lewat 2×</th>
                  <th className="px-4 py-2 text-right">Rata-rata</th>
                  <th className="px-4 py-2 text-right">Median</th>
                  <th className="px-4 py-2 text-right">P90</th>
                  <th className="px-4 py-2 text-right">Terlama</th>
                  <th className="px-4 py-2 text-left">Masuk terlama</th>
                </tr>
              </thead>
              <tbody>
                {(report?.rows || []).map((r) => (
                  <tr key={r.stage} data-testid={AGINGREPORT.row} data-stage={r.stage}
                    className="border-t">
                    <td className="px-4 py-2">
                      <Link data-testid={AGINGREPORT.drill} data-stage={r.stage} to={r.drill}
                        aria-label={`Buka daftar tahap ${r.stage}`}
                        className="font-medium text-primary hover:underline">
                        {labelOf(report.vocab, r.stage) || r.stage || "(tanpa tahap)"}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {r.sla_hours ? formatHours(r.sla_hours) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.count}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {r.over_sla && r.drill_over ? (
                        <Link data-testid={AGINGREPORT.drillOver} data-stage={r.stage}
                          to={r.drill_over} aria-label={`Buka ${r.stage} yang lewat SLA`}
                          className="inline-flex items-center gap-1 font-medium text-amber-700
                            hover:underline">
                          <AlertTriangle className="h-3.5 w-3.5" /> {r.over_sla}
                        </Link>
                      ) : (r.over_sla || 0)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      <span className={r.over2_sla ? "font-medium text-rose-700" : ""}>
                        {r.over2_sla || 0}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatHours(r.avg_stage_age_hours)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatHours(r.p50_stage_age_hours)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatHours(r.p90_stage_age_hours)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatHours(r.max_stage_age_hours)}
                    </td>
                    <td className="px-4 py-2 text-xs text-muted-foreground">
                      {r.oldest_entered_at ? fromNow(r.oldest_entered_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div data-testid={AGINGREPORT.overview} className="rounded-lg border bg-card shadow-[var(--shadow-card)]">
        <div className="border-b px-4 py-3">
          <h3 className="text-sm font-semibold">
            Lintas domain · {overview?.totals?.over_sla || 0} objek lewat SLA
          </h3>
          <p className="text-xs text-muted-foreground">
            Satu tabel untuk semua: lead, deal, tugas, komplain, pembeli, tagihan, dokumen.
          </p>
        </div>
        <div className="grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-4">
          {(overview?.data || []).map((row) => (
            <Link key={row.entity} data-testid={AGINGREPORT.overviewRow} data-entity={row.entity}
              to={row.over_sla ? row.drill_over : row.drill}
              aria-label={`Buka daftar ${row.label}`}
              className="rounded-md border bg-background p-3 hover:border-primary">
              <p className="text-sm font-medium">{row.label}</p>
              <p className="text-xs text-muted-foreground">
                {row.count} baris · <span className={row.over_sla ? "text-amber-700" : ""}>
                  {row.over_sla} lewat SLA
                </span>
                {row.over2_sla ? <span className="text-rose-700"> · {row.over2_sla} lewat 2×</span>
                  : null}
              </p>
              {row.worst_stage ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  paling banyak tertahan: {labelOf(row.vocab, row.worst_stage) || row.worst_stage}
                </p>
              ) : null}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
