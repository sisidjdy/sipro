import React, { useCallback, useEffect, useState } from "react";
import { FileDown, FileText, HandCoins } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import MoneyText from "@/components/patterns/MoneyText";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { downloadCsv } from "@/utils/tableCsv";
import { downloadFile } from "@/utils/fileDownload";
import { formatDateTimeWIB } from "@/utils/formatters";
import { P59 } from "@/constants/testIds";

/**
 * LateFeeWaiverReport — LAPORAN KERINGANAN DENDA (Fase 59).
 *
 * Keringanan sudah berjejak sejak Fase 58, tetapi jejak yang hanya bisa dibaca satu pembeli
 * pada satu waktu tidak bisa dipakai rapat direksi. Laporan ini menjawab empat pertanyaan
 * pengawasan sekaligus: SIAPA yang meringankan, APA yang diringankan, BERAPA, dan ALASANNYA.
 *
 * Dipakai di dua tempat dengan satu komponen (tidak ada laporan kedua yang bisa menyimpang):
 *  * tab "Riwayat keringanan" pada panel denda di Rencana Bayar pembeli (`dealId` diisi);
 *  * tab "Denda & Keringanan" di halaman Keuangan (seluruh organisasi).
 */
const COLUMNS = [
  { key: "unit_code", header: "Unit" },
  { key: "lead_name", header: "Pembeli" },
  { key: "term_label", header: "Termin" },
  { key: "amount", header: "Diringankan (Rp)" },
  { key: "waived_by", header: "Diringankan oleh" },
  { key: "waived_at", header: "Tanggal" },
  { key: "reason", header: "Alasan" },
  { key: "journal_id", header: "Jurnal balik" },
];

export default function LateFeeWaiverReport({ dealId, unitCode }) {
  const { can } = useAuth();
  const mayView = can("late_fee", "view");
  const [scope, setScope] = useState(dealId ? "deal" : "all");
  const [range, setRange] = useState({ from: "", to: "" });
  const [data, setData] = useState(null);
  const [state, setState] = useState({ loading: true, error: "" });
  const [busy, setBusy] = useState(false);

  const params = useCallback(() => ({
    ...(scope === "deal" && dealId ? { deal_id: dealId } : {}),
    ...(range.from ? { date_from: range.from } : {}),
    ...(range.to ? { date_to: range.to } : {}),
  }), [scope, dealId, range]);

  const load = useCallback(async () => {
    setState({ loading: true, error: "" });
    try {
      const res = await api.get("/finance/late-fee-waivers", { params: params() });
      setData(res.data.data);
      setState({ loading: false, error: "" });
    } catch (e) {
      setState({ loading: false,
        error: e?.response?.data?.detail || "Gagal memuat laporan keringanan denda." });
    }
  }, [params]);

  useEffect(() => { if (mayView) load(); }, [mayView, load]);

  if (!mayView) {
    return (
      <p data-testid={P59.waiverDenied}
        className="rounded-lg border bg-secondary/40 px-3 py-2 text-[12px] text-muted-foreground">
        Laporan keringanan denda hanya dibuka untuk peran yang mengurus penagihan. Ini soal
        HAK AKSES, bukan data yang belum ada.
      </p>
    );
  }
  if (state.loading) return <LoadingCards count={2} />;
  if (state.error) return <ErrorState message={state.error} onRetry={load} />;
  if (!data) return null;

  const rows = data.rows || [];
  const t = data.totals || {};

  const exportCsv = () => {
    if (!rows.length) return;
    const n = downloadCsv(COLUMNS, rows, "laporan-keringanan-denda");
    toast.success(`${rows.length} baris keringanan diekspor ke CSV (${n} karakter).`);
  };

  const exportPdf = async () => {
    setBusy(true);
    try {
      const name = await downloadFile("/finance/late-fee-waivers/pdf", {
        params: params(), fallbackName: "laporan-keringanan-denda.pdf" });
      toast.success(`PDF untuk rapat direksi diunduh (${name}).`);
    } catch (e) {
      toast.error("Gagal mengekspor PDF laporan keringanan.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={P59.waiverPanel} className="space-y-3">
      <div data-testid={P59.waiverSummary} className="grid gap-2 sm:grid-cols-4">
        <MetricCard label="Keringanan diberikan" value={t.count || 0}
          hint={`${t.deals || 0} transaksi`} />
        <MetricCard label="Nilai diringankan" value={<MoneyText value={t.amount || 0} />}
          hint="Jurnalnya dibalik (Dr Pendapatan Denda)" />
        <MetricCard label="Pemberi keputusan" value={t.actors || 0}
          hint="Manajer Keuangan yang menandatangani" />
        <MetricCard label="Denda masih tertagih"
          value={<MoneyText value={t.charged_outstanding || 0} />}
          hint="Ditagihkan & belum diringankan" />
      </div>

      <div className="flex flex-wrap items-end gap-2">
        {dealId ? (
          <Button size="sm" variant="outline" data-testid={P59.waiverScope}
            data-scope={scope}
            onClick={() => setScope((s) => (s === "deal" ? "all" : "deal"))}>
            {scope === "deal"
              ? `Hanya unit ${unitCode || "ini"} · lihat semua unit`
              : "Semua unit · kembali ke unit ini"}
          </Button>
        ) : null}
        <div>
          <Label htmlFor="waiver-from" className="text-[11px]">Dari tanggal</Label>
          <Input id="waiver-from" type="date" data-testid={P59.waiverFrom}
            className="h-9 w-[150px] bg-background" value={range.from}
            onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))} />
        </div>
        <div>
          <Label htmlFor="waiver-to" className="text-[11px]">Sampai tanggal</Label>
          <Input id="waiver-to" type="date" data-testid={P59.waiverTo}
            className="h-9 w-[150px] bg-background" value={range.to}
            onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))} />
        </div>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" data-testid={P59.waiverCsvBtn}
            onClick={exportCsv} disabled={!rows.length}>
            <FileDown className="mr-1.5 h-3.5 w-3.5" /> CSV
          </Button>
          <Button size="sm" data-testid={P59.waiverPdfBtn} onClick={exportPdf}
            disabled={busy || !rows.length}>
            <FileText className="mr-1.5 h-3.5 w-3.5" /> {busy ? "Menyiapkan…" : "PDF"}
          </Button>
        </div>
      </div>

      <p className="text-[12px] text-muted-foreground">{data.note}</p>

      {!rows.length ? (
        <div data-testid={P59.waiverEmpty}>
          <EmptyState icon={HandCoins} title="Belum ada keringanan denda"
            description={(range.from || range.to)
              ? "Tidak ada keringanan pada periode yang dipilih. Kosongnya daftar ini karena "
                + "saringan tanggal, bukan karena fitur keringanan belum ada."
              : "Belum ada denda yang diringankan Manajer Keuangan. Ini kabar baik, bukan "
                + "data yang hilang."} />
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Unit / pembeli</TableHead>
                  <TableHead>Termin</TableHead>
                  <TableHead className="text-right">Diringankan</TableHead>
                  <TableHead>Oleh &amp; kapan</TableHead>
                  <TableHead>Alasan tertulis</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.penalty_id} data-testid={P59.waiverRow}>
                    <TableCell className="text-sm">
                      <span className="font-medium">{r.unit_code || "-"}</span>
                      <p className="text-[11px] text-muted-foreground">{r.lead_name || "-"}</p>
                    </TableCell>
                    <TableCell className="text-sm">
                      {r.term_label || "-"}
                      <p className="text-[11px] text-muted-foreground">
                        {r.days_late} hari lewat toleransi · periode {r.period || "-"}
                      </p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <MoneyText value={r.amount} />
                    </TableCell>
                    <TableCell className="text-sm">
                      {r.waived_by || "-"}
                      <p className="text-[11px] text-muted-foreground">
                        {formatDateTimeWIB(r.waived_at)}
                      </p>
                    </TableCell>
                    <TableCell className="max-w-[22rem] text-[12px]">{r.reason}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="space-y-1.5">
            <p className="text-[12px] font-medium">
              Rekapitulasi per pemberi keputusan (yang ditanya di rapat direksi)
            </p>
            {(data.by_actor || []).map((a) => (
              <div key={a.actor} data-testid={P59.waiverActorRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-[12px]">
                <span className="font-medium">{a.actor}</span>
                <span className="text-muted-foreground">{a.count} keringanan</span>
                <span className="font-semibold tabular-nums">
                  <MoneyText value={a.amount} />
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
