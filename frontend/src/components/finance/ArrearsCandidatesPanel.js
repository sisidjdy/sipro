import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlarmClock, ClipboardList, FileWarning, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import MoneyText from "@/components/patterns/MoneyText";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import WarningLetterDialog from "@/components/finance/WarningLetterDialog";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { P59, P62 } from "@/constants/testIds";

/**
 * ArrearsCandidatesPanel — PEMBATALAN KARENA TUNGGAKAN (Fase 59).
 *
 * SPR menuliskan hak developer membatalkan sepihak setelah tunggakan N bulan; sampai Fase 58
 * tidak ada layar yang menunjuk siapa yang sudah melewatinya, jadi pasal itu hanya hidup di
 * kertas. Panel ini MENGUSULKAN — dan sengaja tidak punya tombol "batalkan":
 *
 *  * pembatalan tetap DIAJUKAN Manajer Sales dari tab Kontrak & Legal dan DIPUTUS Manajer
 *    Keuangan (pemisahan tugas Fase 56 tidak boleh dipotong oleh fitur baru);
 *  * tunggakan sering punya sebab yang tidak ada di database — itulah gunanya keringanan;
 *  * setiap baris menyebut aturan & sebab penghalangnya, bukan tombol mati tanpa penjelasan.
 */
const TONE = {
  kandidat_batal: "border-rose-200 bg-rose-50 text-rose-800",
  perhatian: "border-amber-200 bg-amber-50 text-amber-900",
  aman: "border-slate-200 bg-slate-100 text-slate-700",
};

export default function ArrearsCandidatesPanel() {
  const { can } = useAuth();
  const maySweep = can("cancellation", "approve");
  const [data, setData] = useState(null);
  const [state, setState] = useState({ loading: true, error: "" });
  const [busy, setBusy] = useState(false);
  const [warnFor, setWarnFor] = useState(null);

  const load = useCallback(async () => {
    setState({ loading: true, error: "" });
    try {
      const res = await api.get("/finance/arrears/candidates");
      setData(res.data.data);
      setState({ loading: false, error: "" });
    } catch (e) {
      setState({ loading: false,
        error: e?.response?.data?.detail || "Gagal memuat kandidat tunggakan." });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const sweep = async () => {
    setBusy(true);
    try {
      const res = await api.post("/finance/arrears/sweep", {});
      const n = (res.data?.data?.created || []).length;
      toast.success(n
        ? `${n} tugas peninjauan dititipkan ke Manajer Keuangan.`
        : "Tidak ada tugas baru — peninjauan bulan ini sudah pernah dibuat.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menitipkan tugas peninjauan.");
    } finally { setBusy(false); }
  };

  if (state.loading) return <LoadingCards count={2} />;
  if (state.error) return <ErrorState message={state.error} onRetry={load} />;
  if (!data) return null;

  const rows = data.rows || [];
  const t = data.totals || {};

  return (
    <div data-testid={P59.arrearsPanel} className="space-y-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="flex items-center gap-1.5 font-heading text-[13px] font-semibold">
          <AlarmClock className="h-4 w-4 text-rose-600" />
          Kandidat pembatalan karena tunggakan (batas kontrak {data.threshold_months} bulan)
        </p>
        {maySweep && t.count_candidate > 0 ? (
          <Button size="sm" variant="outline" data-testid={P59.arrearsSweepBtn}
            onClick={sweep} disabled={busy}>
            <ClipboardList className="mr-1.5 h-3.5 w-3.5" />
            {busy ? "Menitipkan…" : "Buat tugas peninjauan"}
          </Button>
        ) : null}
      </div>

      <div data-testid={P59.arrearsSummary} className="grid gap-2 sm:grid-cols-3">
        <MetricCard label="Sudah melewati batas" value={t.count_candidate || 0}
          hint={`dari ${t.count || 0} pesanan yang menunggak`} />
        <MetricCard label="Tunggakan kandidat"
          value={<MoneyText value={t.overdue_amount || 0} />}
          hint="Lewat masa toleransi kontrak" />
        <MetricCard label="Denda berjalan kandidat"
          value={<MoneyText value={t.denda_running || 0} />}
          hint="Bisa ditagihkan atau diringankan lebih dulu" />
      </div>

      <p data-testid={P59.arrearsRule} className="text-[12px] text-muted-foreground">
        {data.note}
      </p>

      {!rows.length ? (
        <div data-testid={P59.arrearsEmpty}>
          <EmptyState icon={ShieldCheck} title="Tidak ada tunggakan yang mendekati batas"
            description={"Semua pesanan berada di dalam batas tunggakan yang tertulis di SPR. "
              + "Termin yang lewat tanggal tetapi masih di dalam masa toleransi TIDAK dihitung "
              + "menunggak."} />
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Unit / pembeli</TableHead>
                <TableHead className="text-right">Bulan menunggak</TableHead>
                <TableHead className="text-right">Tunggakan</TableHead>
                <TableHead className="text-right">Denda berjalan</TableHead>
                <TableHead>Tahap</TableHead>
                <TableHead>Yang menghalangi pengajuan</TableHead>
                <TableHead className="col-actions-head" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.deal_id} data-testid={P59.arrearsRow} data-stage={r.stage}>
                  <TableCell className="text-sm">
                    <span className="font-medium">{r.unit_code || "-"}</span>
                    <p className="text-[11px] text-muted-foreground">
                      {r.lead_name || "-"} · {r.contract_number || "tanpa kontrak"}
                    </p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {r.months_in_arrears}
                    <p className="text-[11px] text-muted-foreground">
                      {r.by_terms} termin · {r.max_days_late} hari
                    </p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-rose-700">
                    <MoneyText value={r.overdue_amount} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <MoneyText value={r.denda_running} />
                  </TableCell>
                  <TableCell>
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${TONE[r.stage]}`}>
                      {r.stage_label}
                    </span>
                  </TableCell>
                  <TableCell data-testid={P59.arrearsBlock}
                    className="max-w-[20rem] text-[12px] text-muted-foreground">
                    {r.blocks?.length
                      ? r.blocks.map((b) => b.detail).join(" ")
                      : "Tidak ada penghalang — pengajuan bisa dibuat Manajer Sales."}
                  </TableCell>
                  <TableCell className="col-actions text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="outline" data-testid={P62.warnOpenBtn}
                        onClick={() => setWarnFor(r)}>
                        <FileWarning className="mr-1 h-3.5 w-3.5" /> Surat peringatan
                      </Button>
                      {r.customer_id ? (
                        <Button size="sm" variant="outline" asChild
                          data-testid={P59.arrearsOpenBtn}>
                          <Link to={`/customers/${r.customer_id}?tab=kontrak53`}>Buka kontrak</Link>
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <WarningLetterDialog row={warnFor} open={!!warnFor}
        onOpenChange={(v) => !v && setWarnFor(null)} />
    </div>
  );
}
