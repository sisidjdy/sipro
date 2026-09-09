import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ReceiptText, Download, FileDown, Plus, ShieldAlert, CheckCircle2, AlertTriangle, Pencil, Ban,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import RefLabel from "@/components/patterns/RefLabel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import TaxPeriodBar from "@/components/tax/TaxPeriodBar";
import WithholdingIssueDialog from "@/components/tax/WithholdingIssueDialog";
import WithholdingActionDialog from "@/components/tax/WithholdingActionDialog";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import { downloadFile, blobErrorDetail } from "@/utils/fileDownload";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const thisMonth = () => new Date().toISOString().slice(0, 7);
const TONE = { issued: "active", corrected: "high", cancelled: "cancelled" };

/**
 * Bukti potong PPh / e-Bupot (Fase 49F).
 *
 * Layar ini membedakan dua asal potongan dengan tegas:
 *  1. **Kandidat** — potongan yang BENAR-BENAR sudah terjadi di pembukuan (pembayaran tagihan,
 *     fee mitra) tetapi belum berbukti potong. Pihak yang dipotong belum bisa mengkreditkan
 *     pajaknya, jadi daftar ini adalah daftar kerja, bukan angka hiasan.
 *  2. **Bukti potong terbit** — bernomor tetap, bisa dibetulkan (nomor tidak berubah),
 *     dibatalkan beralasan, dicetak PDF untuk diberikan ke pihak dipotong, dan diekspor.
 *
 * Tie-out di atas tabel membandingkan potongan NYATA vs bukti yang terbit — selisihnya
 * dilaporkan apa adanya.
 */
export default function WithholdingPanel() {
  const { can } = useAuth();
  const canIssue = can("tax", "withholding_issue");
  const canUpdate = can("tax", "update");
  const canExport = can("tax", "export");
  const [period, setPeriod] = useState(thisMonth());
  const [periods, setPeriods] = useState([]);
  const [docs, setDocs] = useState(null);
  const [cands, setCands] = useState(null);
  const [config, setConfig] = useState(null);
  const [check, setCheck] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [issueOpen, setIssueOpen] = useState(false);
  const [action, setAction] = useState(null); // {mode, doc}

  const load = useCallback(async (p) => {
    setLoading(true); setError("");
    try {
      const [list, cand, cfg, chk, per] = await Promise.all([
        api.get("/tax/compliance/withholding", { params: { period: p } }),
        api.get("/tax/compliance/withholding/candidates", { params: { period: p } }),
        api.get("/tax/compliance/withholding/config"),
        api.get("/tax/compliance/withholding-export/check", { params: { period: p } }),
        api.get("/tax/compliance/periods"),
      ]);
      setDocs(list.data || null);
      setCands(cand.data.data || null);
      setConfig(cfg.data.data || null);
      setCheck(chk.data.data || null);
      setPeriods(per.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat bukti potong PPh.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(period); }, [load, period]);

  const issueFromCandidate = async (row) => {
    setBusy(row.ref_id);
    try {
      const res = await api.post("/tax/compliance/withholding/issue", {
        kind: row.kind, basis: row.basis, party_name: row.party_name,
        party_npwp: row.party_npwp || null, party_kind: row.party_kind || "company",
        base: row.base, rate: row.rate, ref_id: row.ref_id, ref_label: row.ref_label,
        date: row.date,
      });
      const doc = res.data.data || {};
      toast.success(doc.idempotent
        ? `Potongan ini sudah punya bukti potong ${doc.number} — tidak dilaporkan dua kali.`
        : `Bukti potong ${doc.number} terbit senilai ${formatIDR(doc.amount)}.`);
      await load(period);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerbitkan bukti potong.");
    } finally { setBusy(""); }
  };

  const openPdf = async (doc) => {
    setBusy(doc.id);
    try {
      await downloadFile(`/tax/compliance/withholding/${doc.id}/pdf`, {
        fallbackName: `bupot-${doc.number}.pdf`, open: true,
      });
    } catch (e) {
      toast.error(await blobErrorDetail(e, "Gagal membuka PDF bukti potong."));
    } finally { setBusy(""); }
  };

  const exportFile = async (format) => {
    setBusy("export");
    try {
      const name = await downloadFile("/tax/compliance/withholding-export/file", {
        params: { period, format },
        fallbackName: `bupot-${period}.${format === "excel_csv" ? "csv" : "xml"}`,
      });
      toast.success(`Berkas ${name} diunduh.`);
    } catch (e) {
      toast.error(await blobErrorDetail(e, "Ekspor bukti potong gagal."));
    } finally { setBusy(""); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={() => load(period)} />;

  const rows = docs?.data || [];
  const sum = docs?.summary || {};
  const tie = docs?.tie_out || {};
  const blocking = check?.blocking || [];
  const warnings = check?.warnings || [];
  const ready = !!check?.can_export;

  return (
    <div data-testid={P49.bupotPanel} className="space-y-4">
      <TaxPeriodBar period={period} onChange={setPeriod} periods={periods}
        inputId="p49-bupot-month" inputTestId={P49.bupotPeriod} quickTestId={P49.bupotPeriodQuick}
        onRefresh={() => load(period)}>
        {canIssue ? (
          <Button type="button" size="sm" className="h-8 text-xs" data-testid={P49.bupotIssueBtn}
            onClick={() => setIssueOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Bukti Potong Manual
          </Button>
        ) : null}
      </TaxPeriodBar>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <MetricCard label="Bukti potong aktif" value={`${sum.alive || 0} dari ${sum.total || 0}`}
          tone="primary" hint={`${sum.corrected || 0} dibetulkan · ${sum.cancelled || 0} dibatalkan`} />
        <MetricCard label="Nilai potongan terbukti" value={sum.amount} format="idr" tone="emerald" />
        <MetricCard label="Dasar pengenaan" value={sum.base} format="idr" tone="sky" />
        <MetricCard label="Belum berbukti potong" value={tie.unproven} format="idr"
          tone={tie.matches ? "emerald" : "rose"}
          hint={`${cands?.count || 0} potongan menunggu`} />
        <MetricCard label="NPWP pemotong" value={config?.company_npwp || "belum diisi"}
          tone={config?.company_npwp ? "emerald" : "rose"}
          hint={`Seri ${config?.series || "-"} · ${config?.company_name || ""}`} />
      </div>

      <div data-testid={P49.bupotTieOut} data-matches={String(!!tie.matches)}
        className={`flex flex-wrap items-start gap-2 rounded-xl border p-3.5 text-sm ${tie.matches
          ? "border-emerald-200 bg-emerald-50 text-emerald-900"
          : "border-amber-200 bg-amber-50 text-amber-900"}`}>
        {tie.matches ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
        <div className="min-w-0">
          <p className="font-medium">{tie.detail}</p>
          <p className="text-xs tabular-nums">
            Potongan nyata di pembukuan {formatIDR(tie.actual)} · sudah berbukti potong {formatIDR(tie.issued)}
          </p>
          <p className="text-[11px]">{docs?.note}</p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="font-heading text-sm font-semibold">
          Potongan PPh yang belum berbukti potong ({cands?.count || 0})
        </p>
        <p className="text-xs text-muted-foreground">{cands?.detail}</p>
        {(cands?.rows || []).length ? (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Pihak dipotong</TableHead>
                <TableHead>Asal potongan</TableHead>
                <TableHead>Jenis</TableHead>
                <TableHead className="text-right">Dasar</TableHead>
                <TableHead className="text-right">Tarif</TableHead>
                <TableHead className="text-right">Potongan</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {cands.rows.map((r) => (
                  <TableRow key={`${r.basis}_${r.ref_id}`} data-testid={P49.bupotCandidateRow}
                    data-ref={r.ref_id}>
                    <TableCell className="text-sm font-medium">
                      {r.party_name}
                      <p className="text-[11px] font-normal text-muted-foreground">
                        {r.party_npwp || "NPWP belum ada"} · {formatDateWIB(r.date)}
                      </p>
                    </TableCell>
                    <TableCell className="text-xs">
                      <RefLabel group="withholding_basis" value={r.basis} />
                      <p className="text-[11px] text-muted-foreground">{r.ref_label}</p>
                    </TableCell>
                    <TableCell className="text-xs">
                      <RefLabel group="withholding_kind" value={r.kind} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.base)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{r.rate}%</TableCell>
                    <TableCell className="text-right tabular-nums text-sm font-semibold">
                      {formatIDR(r.amount)}
                    </TableCell>
                    <TableCell className="col-actions text-right">
                      {canIssue ? (
                        <Button size="sm" data-testid={P49.bupotCandidateIssueBtn} data-ref={r.ref_id}
                          disabled={busy === r.ref_id} onClick={() => issueFromCandidate(r)}>
                          <ReceiptText className="mr-1 h-3.5 w-3.5" /> Terbitkan
                        </Button>
                      ) : <span className="text-[11px] text-muted-foreground">khusus Keuangan</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </div>

      <div className={`space-y-2 rounded-xl border p-3.5 text-sm ${ready
        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
        : "border-amber-200 bg-amber-50 text-amber-900"}`}>
        <p className="flex items-center gap-1.5 font-semibold">
          {ready ? <CheckCircle2 className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
          {check?.detail}
        </p>
        {blocking.length ? (
          <ul className="list-disc space-y-1 pl-5 text-xs" data-testid={P49.bupotExportBlocking}>
            {blocking.map((b, i) => (
              <li key={`${b.number || b.scope}_${i}`}>
                <span className="font-medium">{b.number || "NPWP perusahaan"}</span> — {b.reason}
              </li>
            ))}
          </ul>
        ) : null}
        {warnings.length ? (
          <ul className="list-disc space-y-1 pl-5 text-xs">
            {warnings.map((w, i) => (
              <li key={`${w.number}_${i}`}><span className="font-medium">{w.number}</span> — {w.reason}</li>
            ))}
          </ul>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button size="sm" data-testid={P49.bupotExportXmlBtn}
            disabled={busy === "export" || !ready || !canExport} onClick={() => exportFile("coretax_xml")}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Unduh XML (e-Bupot)
          </Button>
          <Button size="sm" variant="outline" data-testid={P49.bupotExportCsvBtn}
            disabled={busy === "export" || !ready || !canExport} onClick={() => exportFile("excel_csv")}>
            <FileDown className="mr-1.5 h-3.5 w-3.5" /> Unduh CSV
          </Button>
        </div>
        <p className="text-[11px]">{check?.note}</p>
      </div>

      {!rows.length ? (
        <EmptyState icon={ReceiptText} title="Belum ada bukti potong pada masa ini"
          description="Bukti potong terbit otomatis saat tagihan dibayar dengan potong PPh, atau bisa diterbitkan manual dari daftar kandidat di atas." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Nomor</TableHead>
              <TableHead>Pihak dipotong</TableHead>
              <TableHead>Jenis / asal</TableHead>
              <TableHead className="text-right">Dasar</TableHead>
              <TableHead className="text-right">Tarif</TableHead>
              <TableHead className="text-right">Potongan</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="col-actions-head text-right">Aksi</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((d) => (
                <TableRow key={d.id} data-testid={P49.bupotRow} data-number={d.number}
                  data-state={d.state}>
                  <TableCell className="text-sm font-medium tabular-nums">
                    {d.number}
                    <p className="text-[11px] font-normal text-muted-foreground">
                      versi {d.version} · {formatDateWIB(d.date)}
                    </p>
                  </TableCell>
                  <TableCell className="text-sm">
                    {d.party_name}
                    <p className={`text-[11px] ${d.npwp_ok ? "text-muted-foreground" : "text-rose-700"}`}>
                      {d.party_npwp || "NPWP belum diisi"}
                      {!d.npwp_ok && d.npwp_note ? ` — ${d.npwp_note}` : ""}
                    </p>
                  </TableCell>
                  <TableCell className="text-xs">
                    {d.kind_label}
                    <p className="text-[11px] text-muted-foreground">
                      {d.basis_label}{d.ref_label ? ` · ${d.ref_label}` : ""}
                    </p>
                    {d.object_code ? (
                      <p className="text-[11px] tabular-nums text-muted-foreground">objek {d.object_code}</p>
                    ) : (
                      <p className="text-[11px] text-amber-700">kode objek belum diisi</p>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(d.base)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{d.rate}%</TableCell>
                  <TableCell className="text-right tabular-nums text-sm font-semibold text-primary">
                    {formatIDR(d.amount)}
                  </TableCell>
                  <TableCell>
                    <StatusPill status={d.state} group="withholding_state"
                      tone={TONE[d.state] || "active"} />
                    {d.cancel_reason ? (
                      <p className="mt-1 max-w-[180px] text-[11px] text-rose-700">{d.cancel_reason}</p>
                    ) : null}
                  </TableCell>
                  <TableCell className="col-actions">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Button size="sm" variant="outline" data-testid={P49.bupotPdfBtn}
                        data-number={d.number} disabled={busy === d.id} onClick={() => openPdf(d)}>
                        <FileDown className="mr-1 h-3.5 w-3.5" /> PDF
                      </Button>
                      {canUpdate && d.state !== "cancelled" ? (
                        <>
                          <Button size="sm" variant="outline" data-testid={P49.bupotCorrectBtn}
                            data-number={d.number} onClick={() => setAction({ mode: "correct", doc: d })}>
                            <Pencil className="mr-1 h-3.5 w-3.5" /> Betulkan
                          </Button>
                          <Button size="sm" variant="outline" data-testid={P49.bupotCancelBtn}
                            data-number={d.number} onClick={() => setAction({ mode: "cancel", doc: d })}>
                            <Ban className="mr-1 h-3.5 w-3.5" /> Batalkan
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <WithholdingIssueDialog open={issueOpen} onOpenChange={setIssueOpen} config={config}
        onDone={() => load(period)} />
      <WithholdingActionDialog mode={action?.mode} doc={action?.doc} open={!!action}
        onOpenChange={(v) => !v && setAction(null)} onDone={() => load(period)} />
    </div>
  );
}
