import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  FileText, Download, ShieldAlert, CheckCircle2, RefreshCcw, Ban, Info,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import TaxPeriodBar from "@/components/tax/TaxPeriodBar";
import FakturActionDialog from "@/components/tax/FakturActionDialog";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import { downloadFile, blobErrorDetail } from "@/utils/fileDownload";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const thisMonth = () => new Date().toISOString().slice(0, 7);
const TONE = { issued: "active", replaced: "high", cancelled: "cancelled" };

/**
 * e-Faktur: pengganti, pembatalan, dan EKSPOR yang menahan diri (Fase 49E).
 *
 * Aturan yang dipertahankan di layar: berkas ekspor TIDAK PERNAH dibuat setengah lengkap.
 * Bila NPWP perusahaan atau NPWP pembeli belum ada, tombol unduh dimatikan dan layar
 * menyebut faktur mana yang harus dilengkapi — termasuk bila server menolak (409), pesannya
 * dibaca dari jawaban berkas supaya sebabnya tetap terbaca.
 */
export default function FakturExportPanel() {
  const { can } = useAuth();
  const canUpdate = can("tax", "update");
  const canExport = can("tax", "export");
  const [period, setPeriod] = useState(thisMonth());
  const [periods, setPeriods] = useState([]);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [check, setCheck] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [held, setHeld] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState(null); // {mode, faktur}
  // Masa berjalan sering masih kosong (faktur diterbitkan di masa sebelumnya). Sekali saja,
  // layar berpindah ke masa TERBARU yang benar-benar punya faktur supaya pemakai tidak
  // menyimpulkan "tidak ada data" dari bulan yang memang belum ada transaksinya.
  const autoPick = useRef(true);

  const load = useCallback(async (p) => {
    setLoading(true); setError(""); setHeld("");
    try {
      const [list, chk, per] = await Promise.all([
        api.get("/tax/compliance/faktur", { params: { period: p } }),
        api.get("/tax/compliance/faktur-export/check", { params: { period: p } }),
        api.get("/tax/compliance/faktur/periods"),
      ]);
      const known = per.data.data || [];
      setRows(list.data.data || []);
      setSummary(list.data.summary || null);
      setCheck(chk.data.data || null);
      setPeriods(known);
      if (autoPick.current) {
        autoPick.current = false;
        if (!known.includes(p) && known.length) setPeriod(known[0]);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat faktur pajak keluaran.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(period); }, [load, period]);

  const exportFile = async (format) => {
    setBusy(true); setHeld("");
    try {
      const name = await downloadFile("/tax/compliance/faktur-export/file", {
        params: { period, format },
        fallbackName: `faktur-${period}.${format === "excel_csv" ? "csv" : "xml"}`,
      });
      toast.success(`Berkas ${name} diunduh.`);
    } catch (e) {
      const detail = await blobErrorDetail(e, "Ekspor faktur gagal.");
      setHeld(detail);
      toast.error(detail);
    } finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={() => load(period)} />;

  const blocking = check?.blocking || [];
  const ready = !!check?.can_export;

  return (
    <div data-testid={P49.fakturExportPanel} className="space-y-4">
      <TaxPeriodBar period={period} onChange={setPeriod} periods={periods}
        inputId="p49-faktur-export-month" inputTestId={P49.fakturExportPeriod}
        quickTestId={P49.fakturExportPeriodQuick} onRefresh={() => load(period)}>
        <Button type="button" size="sm" variant="outline" className="h-8 text-xs"
          data-testid={P49.fakturExportCheckBtn} onClick={() => load(period)}>
          <RefreshCcw className="mr-1 h-3.5 w-3.5" /> Cek Kesiapan Ekspor
        </Button>
      </TaxPeriodBar>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <MetricCard label="Faktur aktif" value={`${summary?.active || 0} dari ${summary?.total || 0}`}
          tone="primary" hint={`${summary?.replaced || 0} diganti · ${summary?.cancelled || 0} batal`} />
        <MetricCard label="DPP masa ini" value={summary?.dpp} format="idr" tone="sky" />
        <MetricCard label="PPN keluaran" value={summary?.ppn} format="idr" tone="emerald" />
        <MetricCard label="Identitas belum lengkap" value={`${summary?.incomplete || 0} faktur`}
          tone={(summary?.incomplete || 0) ? "rose" : "emerald"}
          hint={(summary?.incomplete || 0) ? "Ekspor ditahan sampai dilengkapi" : "Semua NPWP pembeli lengkap"} />
        <MetricCard label="NPWP pemungut" value={check?.company?.npwp || "belum diisi"}
          tone={check?.company?.npwp ? "emerald" : "rose"}
          hint={check?.company?.name} />
      </div>

      <div className={`space-y-2 rounded-xl border p-3.5 text-sm ${ready
        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
        : "border-amber-200 bg-amber-50 text-amber-900"}`}>
        <p className="flex items-center gap-1.5 font-semibold">
          {ready ? <CheckCircle2 className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
          {check?.detail}
        </p>
        {blocking.length ? (
          <ul className="list-disc space-y-1 pl-5 text-xs" data-testid={P49.fakturExportBlocking}>
            {blocking.map((b, i) => (
              <li key={`${b.number || b.scope}_${i}`}>
                <span className="font-medium">{b.number || "NPWP perusahaan"}</span>
                {b.buyer_name ? ` (${b.buyer_name})` : ""} — {b.reason}
              </li>
            ))}
          </ul>
        ) : null}
        {(check?.normalized || []).length ? (
          <ul className="list-disc space-y-1 pl-5 text-xs" data-testid={P49.fakturExportWarning}>
            {check.normalized.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button size="sm" data-testid={P49.fakturExportXmlBtn} disabled={busy || !ready || !canExport}
            onClick={() => exportFile("coretax_xml")}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Unduh XML (Coretax)
          </Button>
          <Button size="sm" variant="outline" data-testid={P49.fakturExportCsvBtn}
            disabled={busy || !ready || !canExport} onClick={() => exportFile("excel_csv")}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Unduh CSV (template Excel)
          </Button>
          {!canExport ? (
            <span className="text-xs">Mengeluarkan berkas pajak hanya untuk peran Keuangan.</span>
          ) : null}
        </div>
        <p className="flex items-start gap-1.5 text-[11px]">
          <Info className="mt-0.5 h-3 w-3 shrink-0" /> {check?.note}
        </p>
      </div>

      {held ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-sm text-rose-900">
          <p className="font-semibold">Ekspor ditahan server — sebabnya:</p>
          <p className="mt-1">{held}</p>
        </div>
      ) : null}

      {!rows.length ? (
        <EmptyState icon={FileText} title="Belum ada faktur pada masa ini"
          description="Terbitkan faktur pajak keluaran di tab Faktur Pajak, lalu masa ini bisa diekspor ke Coretax." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader><TableRow>
              <TableHead>No. Seri</TableHead>
              <TableHead>Pembeli</TableHead>
              <TableHead>NPWP</TableHead>
              <TableHead className="text-right">DPP</TableHead>
              <TableHead className="text-right">PPN</TableHead>
              <TableHead>Terbit</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Jejak</TableHead>
              <TableHead className="col-actions-head text-right">Aksi</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((f) => (
                <TableRow key={f.id} data-testid={P49.fakturRow} data-number={f.number}
                  data-status={f.status || "issued"}>
                  <TableCell className="text-sm font-medium tabular-nums">{f.number}</TableCell>
                  <TableCell className="text-sm">{f.buyer_name || "-"}</TableCell>
                  <TableCell className="text-sm tabular-nums">
                    <span className={f.npwp_ok ? "text-muted-foreground" : "font-medium text-rose-700"}>
                      {f.buyer_npwp || "belum diisi"}
                    </span>
                    {!f.npwp_ok && f.npwp_note ? (
                      <p className="text-[11px] text-rose-700">{f.npwp_note}</p>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(f.dpp)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm font-semibold text-primary">
                    {formatIDR(f.ppn)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{formatDateWIB(f.issued_at)}</TableCell>
                  <TableCell>
                    <StatusPill status={f.status || "issued"} group="faktur_state"
                      tone={TONE[f.status] || "active"} />
                  </TableCell>
                  <TableCell className="max-w-[220px] text-[11px] text-muted-foreground">
                    {f.replaced_by_number ? <p>Diganti oleh {f.replaced_by_number}</p> : null}
                    {f.replaces_number ? <p>Mengganti {f.replaces_number}</p> : null}
                    {f.cancel_reason ? <p className="text-rose-700">Batal: {f.cancel_reason}</p> : null}
                    {!f.replaced_by_number && !f.replaces_number && !f.cancel_reason ? "—" : null}
                  </TableCell>
                  <TableCell className="col-actions">
                    <div className="flex justify-end gap-1.5">
                      {canUpdate && (f.status || "issued") === "issued" ? (
                        <>
                          <Button size="sm" variant="outline" data-testid={P49.fakturReplaceBtn}
                            data-number={f.number} onClick={() => setDialog({ mode: "replace", faktur: f })}>
                            <RefreshCcw className="mr-1 h-3.5 w-3.5" /> Ganti
                          </Button>
                          <Button size="sm" variant="outline" data-testid={P49.fakturCancelBtn}
                            data-number={f.number} onClick={() => setDialog({ mode: "cancel", faktur: f })}>
                            <Ban className="mr-1 h-3.5 w-3.5" /> Batalkan
                          </Button>
                        </>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">tidak ada aksi</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <FakturActionDialog mode={dialog?.mode} faktur={dialog?.faktur} open={!!dialog}
        onOpenChange={(v) => !v && setDialog(null)} onDone={() => load(period)} />
    </div>
  );
}
