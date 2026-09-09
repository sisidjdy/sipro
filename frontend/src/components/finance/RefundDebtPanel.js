import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BadgeCheck, FileDown, FileText, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import MoneyText from "@/components/patterns/MoneyText";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { downloadCsv } from "@/utils/tableCsv";
import { downloadFile } from "@/utils/fileDownload";
import { formatDateWIB } from "@/utils/formatters";
import { P59 } from "@/constants/testIds";

/**
 * RefundDebtPanel — LAPORAN UTANG REFUND (akun 2-1460) + PROYEKSI KASNYA (Fase 59).
 *
 * Sisa refund sebelumnya hanya bisa dilihat sebagai penjumlahan baris yang sedang tampil di
 * tab Pembatalan — angkanya berubah begitu daftar disaring, dan tidak ada satu pun tanggal.
 * Panel ini menjawab pertanyaan kas yang sebenarnya: KAPAN uang ini harus keluar, sudah
 * berapa lama ia menjadi kewajiban, dan apakah jumlahnya SAMA dengan buku besar.
 *
 * Kejujuran yang dipegang: utang yang tertahan ketentuan SPR (menunggu unit terjual kembali)
 * TIDAK diberi tanggal karangan — ia muncul sebagai "belum bisa dijadwalkan" beserta
 * sebabnya, dan tetap dihitung dalam total kewajiban.
 */
const TONE = {
  terlewat: "border-rose-200 bg-rose-50 text-rose-800",
  segera: "border-amber-200 bg-amber-50 text-amber-900",
  terjadwal: "border-slate-200 bg-slate-100 text-slate-700",
  tertahan: "border-indigo-200 bg-indigo-50 text-indigo-800",
};

const COLUMNS = [
  { key: "number", header: "Nomor" },
  { key: "customer_name", header: "Pembeli" },
  { key: "unit_code", header: "Unit" },
  { key: "decided_at", header: "Tanggal keputusan" },
  { key: "due_date", header: "Jatuh tempo",
    exportValue: (r) => r.due_date || "belum bisa dijadwalkan" },
  { key: "due_state_label", header: "Keadaan" },
  { key: "age_bucket_label", header: "Umur" },
  { key: "refund_outstanding", header: "Sisa utang (Rp)" },
];

export default function RefundDebtPanel() {
  const [data, setData] = useState(null);
  const [state, setState] = useState({ loading: true, error: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setState({ loading: true, error: "" });
    try {
      const res = await api.get("/finance/refund-debt", { params: { horizon: 6 } });
      setData(res.data.data);
      setState({ loading: false, error: "" });
    } catch (e) {
      setState({ loading: false,
        error: e?.response?.data?.detail || "Gagal memuat laporan utang refund." });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (state.loading) return <LoadingCards count={3} />;
  if (state.error) return <ErrorState message={state.error} onRetry={load} />;
  if (!data) return null;

  const rows = data.rows || [];
  const t = data.totals || {};
  const led = data.ledger || {};
  const proj = data.projection || {};

  const exportCsv = () => {
    if (!rows.length) return;
    downloadCsv(COLUMNS, rows, "laporan-utang-refund");
    toast.success(`${rows.length} kewajiban refund diekspor ke CSV.`);
  };

  const exportPdf = async () => {
    setBusy(true);
    try {
      const name = await downloadFile("/finance/refund-debt/pdf",
        { params: { horizon: 6 }, fallbackName: "laporan-utang-refund.pdf" });
      toast.success(`PDF diunduh (${name}).`);
    } catch (e) {
      toast.error("Gagal mengekspor PDF utang refund.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={P59.refundPanel} className="space-y-4">
      <div data-testid={P59.refundSummary} className="grid gap-3 sm:grid-cols-4">
        <MetricCard label="Utang refund belum dibayar"
          value={<MoneyText value={t.outstanding || 0} />}
          hint={`${t.count || 0} kewajiban · akun ${led.account_code || "2-1460"}`} />
        <MetricCard label="Lewat jatuh tempo" value={<MoneyText value={t.overdue || 0} />}
          hint={`Batas ${data.due_days} hari sejak keputusan`} />
        <MetricCard label="Jatuh tempo ≤ 7 hari"
          value={<MoneyText value={t.due_soon || 0} />} hint="Siapkan kas" />
        <MetricCard label="Tertahan ketentuan SPR"
          value={<MoneyText value={t.held || 0} />} hint="Menunggu unit terjual kembali" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12px] text-muted-foreground">{data.note}</p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" data-testid={P59.refundCsvBtn}
            onClick={exportCsv} disabled={!rows.length}>
            <FileDown className="mr-1.5 h-3.5 w-3.5" /> CSV
          </Button>
          <Button size="sm" data-testid={P59.refundPdfBtn} onClick={exportPdf}
            disabled={busy || !rows.length}>
            <FileText className="mr-1.5 h-3.5 w-3.5" /> {busy ? "Menyiapkan…" : "PDF"}
          </Button>
        </div>
      </div>

      <div data-testid={P59.refundLedger}
        className={`rounded-lg border px-3 py-2 text-[12px] ${led.matched
          ? "border-emerald-200 bg-emerald-50 text-emerald-900"
          : "border-rose-200 bg-rose-50 text-rose-900"}`}>
        <p className="flex items-center gap-1.5 font-medium">
          <BadgeCheck className="h-4 w-4" />
          {led.matched
            ? `Cocok dengan buku besar: saldo ${led.account_code} = jumlah sisa refund dokumen`
            : `TIDAK cocok dengan buku besar (selisih ${led.difference?.toLocaleString("id-ID")})`}
        </p>
        <p className="mt-0.5">
          Saldo {led.account_code} <MoneyText value={led.balance || 0} /> · dokumen{" "}
          <MoneyText value={led.worksheet || 0} />. {led.note}
        </p>
      </div>

      <div data-testid={P59.refundBuckets} className="grid gap-2 sm:grid-cols-4">
        {Object.entries(data.buckets || {}).map(([k, v]) => (
          <div key={k} className="rounded-lg border bg-secondary/40 px-2.5 py-1.5">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Umur {k} hari
            </p>
            <p className="font-semibold tabular-nums"><MoneyText value={v} /></p>
          </div>
        ))}
      </div>

      <div data-testid={P59.refundProjection} className="space-y-1.5">
        <p className="text-[12px] font-medium">Proyeksi kas keluar (6 bulan, dari jatuh tempo)</p>
        <div className="grid gap-2 sm:grid-cols-6">
          {(proj.periods || []).map((p) => (
            <div key={p.label} className="rounded-lg border bg-card px-2.5 py-1.5 shadow-[var(--shadow-card)]">
              <p className="text-[11px] text-muted-foreground">{p.label}</p>
              <p className="font-semibold tabular-nums"><MoneyText value={p.outflow} /></p>
            </div>
          ))}
        </div>
        {proj.unscheduled ? (
          <p data-testid={P59.refundUnscheduled}
            className="rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-2 text-[12px] text-indigo-900">
            <b>Belum bisa dijadwalkan <MoneyText value={proj.unscheduled} />.</b>{" "}
            {proj.unscheduled_note}
          </p>
        ) : null}
      </div>

      {!rows.length ? (
        <div data-testid={P59.refundEmpty}>
          <EmptyState icon={Wallet} title="Tidak ada utang refund yang belum dibayar"
            description={"Semua pembatalan yang sudah diputus telah dibayar penuh — akun "
              + "2-1460 bersih. Ini kabar baik, bukan data yang hilang."} />
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nomor</TableHead>
                <TableHead>Pembeli / unit</TableHead>
                <TableHead>Diputus</TableHead>
                <TableHead>Jatuh tempo</TableHead>
                <TableHead>Keadaan</TableHead>
                <TableHead className="text-right">Umur</TableHead>
                <TableHead className="text-right">Sisa utang</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={P59.refundRow} data-state={r.due_state}>
                  <TableCell className="font-mono text-xs">{r.number}</TableCell>
                  <TableCell className="text-sm">
                    {r.customer_id ? (
                      <Link className="text-primary hover:underline"
                        to={`/customers/${r.customer_id}?tab=kontrak53`}>
                        {r.customer_name}
                      </Link>
                    ) : r.customer_name}
                    <p className="text-[11px] text-muted-foreground">unit {r.unit_code}</p>
                  </TableCell>
                  <TableCell className="text-[12px] text-muted-foreground">
                    {formatDateWIB(r.decided_at)}
                  </TableCell>
                  <TableCell className="text-[12px]">
                    {r.due_date ? formatDateWIB(r.due_date) : (
                      <span className="text-muted-foreground">belum bisa dijadwalkan</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${TONE[r.due_state]}`}>
                      {r.due_state_label}
                    </span>
                    {r.hold ? (
                      <p className="mt-0.5 max-w-[18rem] text-[11px] text-muted-foreground">
                        {r.hold.detail}
                      </p>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right text-[12px] tabular-nums">
                    {r.age_days} hari
                    <p className="text-[11px] text-muted-foreground">{r.age_bucket}</p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">
                    <MoneyText value={r.refund_outstanding} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
