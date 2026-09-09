import React, { useCallback, useEffect, useState } from "react";
import { FileText, HandCoins, Landmark, Printer, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import AllinAmendmentBox from "@/components/contracts/AllinAmendmentBox";
import api from "@/services/apiClient";
import { downloadFile } from "@/utils/fileDownload";
import { formatIDR } from "@/utils/formatters";
import { P75 } from "@/constants/testIds";

/**
 * CostBillingPanel — biaya pass-through: invoice biaya (seri INB) → kuitansi biaya (KWB) → titipan →
 * penyaluran ke notaris/BPN. Biaya developer_borne: beban penjualan lewat AP. Tidak menyentuh AR unit.
 */
export default function CostBillingPanel({ contract, onChanged }) {
  const { can } = useAuth();
  const mayFinance = can("finance", "create");
  const [led, setLed] = useState(null);
  const [dlg, setDlgRaw] = useState(null);
  const lastDlg = React.useRef(null);
  const setDlg = (d) => { if (d) lastDlg.current = d; setDlgRaw(d); };
  const view = dlg || lastDlg.current;
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get(`/contracts/${contract.id}/costs-ledger`).then((r) => setLed(r.data.data)).catch(() => setLed(null));
  }, [contract.id]);
  useEffect(() => { load(); }, [load]);

  if (!led || !(led.components || []).length) return null;

  const run = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); setDlg(null); setForm({}); load(); } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memproses.");
    } finally { setBusy(false); }
  };
  const issue = () => run(() => api.post(`/contracts/${contract.id}/cost-invoices`), "Invoice biaya terbit.");
  const pay = () => run(() => api.post(`/cost-invoices/${dlg.inv.id}/pay`, { amount: Number(form.amount) || 0, method: form.method || "transfer", note: form.note }), "Kuitansi biaya terbit → titipan bertambah.");
  const disburse = () => run(() => api.post(`/contracts/${contract.id}/cost-disbursements`, { component_code: dlg.comp.code, amount: Number(form.amount) || 0, payee: form.payee, note: form.note }), "Titipan disalurkan (Titipan / Kas).");
  const expense = () => run(() => api.post(`/contracts/${contract.id}/cost-expenses`, { component_code: dlg.comp.code, amount: Number(form.amount) || dlg.comp.amount, vendor: form.payee, note: form.note }), "Beban penjualan dicatat lewat AP.");

  const openInv = (led.invoices || []).find((i) => i.status !== "void");
  const pdf = (url, name) => downloadFile(url, { fallbackName: name, open: true }).catch((e) => toast.error(e?.response?.data?.detail || "Gagal membuka PDF."));
  const devComps = led.components.filter((c) => c.treatment === "developer_borne");
  const ptComps = led.components.filter((c) => c.treatment === "customer_pass_through");
  const expensed = new Set((led.expenses || []).map((e) => e.component_code));

  return (
    <section data-testid={P75.costPanel} className="space-y-3 rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 font-heading text-base font-semibold"><Wallet className="h-4 w-4" /> Biaya transaksi & titipan</h3>
          <p className="text-xs text-muted-foreground">Skema {contract.costs?.scheme_name || "-"} · biaya TIDAK masuk piutang unit. Titipan = kewajiban, bukan pendapatan.</p>
        </div>
        <div className="text-right text-xs">
          <p>Sisa titipan <strong data-testid={P75.costTitipan}>{formatIDR(led.titipan_balance)}</strong></p>
          <p className="text-muted-foreground">diterima {formatIDR(led.received)} · disalurkan {formatIDR(led.paid_out)}</p>
        </div>
      </div>

      {ptComps.length ? (
        <div className="space-y-2 rounded-lg border bg-background p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground"><FileText className="h-3.5 w-3.5" /> Ditagih ke pembeli (pass-through) · {formatIDR(led.pass_through_total)}</p>
          {ptComps.map((c) => (
            <div key={c.code} className="flex items-center justify-between text-sm">
              <span>{c.name} <span className="text-[11px] text-muted-foreground">· {c.formula}</span></span>
              <span className="flex items-center gap-2 tabular-nums">{formatIDR(c.amount)}
                {mayFinance && led.titipan_balance > 0 ? (
                  <Button data-testid={P75.costDisburseBtn} size="sm" variant="ghost" className="h-6 px-2 text-xs"
                    onClick={() => { setForm({ amount: String(Math.min(c.amount, led.titipan_balance)) }); setDlg({ kind: "disburse", comp: c }); }}>
                    <Landmark className="mr-1 h-3 w-3" /> Salurkan
                  </Button>
                ) : null}
              </span>
            </div>
          ))}
          {!openInv ? (
            mayFinance ? <Button data-testid={P75.costIssueInvoice} size="sm" onClick={issue} disabled={busy}>Terbitkan invoice biaya</Button>
              : <p className="text-xs text-muted-foreground">Invoice biaya belum terbit.</p>
          ) : (
            <div data-testid={P75.costInvoiceRow} data-status={openInv.status} className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-sm">
              <span>Invoice biaya <b className="font-mono">{openInv.number}</b> · {openInv.status} · sisa {formatIDR(openInv.outstanding)}</span>
              <span className="flex items-center gap-1">
                <Button data-testid={P75.costInvoicePdf} size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => pdf(`/cost-invoices/${openInv.id}/pdf`, "invoice-biaya.pdf")}>
                  <Printer className="mr-1 h-3.5 w-3.5" /> PDF
                </Button>
                {mayFinance && openInv.outstanding > 0 ? (
                  <Button data-testid={P75.costPayBtn} size="sm" variant="outline" onClick={() => { setForm({ amount: String(openInv.outstanding) }); setDlg({ kind: "pay", inv: openInv }); }}>
                    <HandCoins className="mr-1 h-3.5 w-3.5" /> Terima pembayaran
                  </Button>
                ) : null}
              </span>
            </div>
          )}
          {(led.receipts || []).map((r) => (
            <p key={r.id} data-testid={P75.costReceiptRow} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Kuitansi biaya <b className="font-mono">{r.receipt_no}</b> · {formatIDR(r.amount)} · {r.method}</span>
              <button type="button" data-testid={P75.costReceiptPdf} className="inline-flex items-center text-primary underline-offset-2 hover:underline"
                onClick={() => pdf(`/cost-receipts/${r.id}/pdf`, "kuitansi-biaya.pdf")}><Printer className="mr-0.5 h-3 w-3" /> PDF</button>
            </p>
          ))}
          {(led.disbursements || []).map((d) => (
            <p key={d.id} className="text-xs text-muted-foreground">Disalurkan {formatIDR(d.amount)} ke {d.payee} ({d.component_code})</p>
          ))}
        </div>
      ) : null}

      {devComps.length ? (
        <div className="space-y-2 rounded-lg border bg-background p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Ditanggung developer (all-in) · {formatIDR(led.developer_borne_total)} · dibebankan {formatIDR(led.developer_expensed)}</p>
          {devComps.map((c) => (
            <div key={c.code} className="flex items-center justify-between text-sm">
              <span>{c.name} <span className="text-[11px] text-muted-foreground">· tidak ditagih ke pembeli</span></span>
              <span className="flex items-center gap-2 tabular-nums">{formatIDR(c.amount)}
                {expensed.has(c.code) ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] text-emerald-800">beban dicatat (AP)</span>
                  : mayFinance ? (
                    <Button data-testid={P75.costExpenseBtn} size="sm" variant="ghost" className="h-6 px-2 text-xs"
                      onClick={() => { setForm({ amount: String(c.amount) }); setDlg({ kind: "expense", comp: c }); }}>Catat beban (AP)</Button>
                  ) : null}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <AllinAmendmentBox contract={contract} onChanged={() => { load(); onChanged && onChanged(); }} />

      <Dialog open={!!dlg} onOpenChange={(v) => !v && setDlg(null)}>
        <DialogContent className="max-w-md bg-background">
          <DialogHeader>
            <DialogTitle>{view?.kind === "pay" ? "Terima pembayaran biaya" : view?.kind === "disburse" ? `Salurkan titipan ${view.comp.name}` : `Catat beban ${view?.comp?.name || ""}`}</DialogTitle>
            <DialogDescription>
              {view?.kind === "pay" ? "Kuitansi biaya seri KWB → jurnal Kas / Titipan biaya customer."
                : view?.kind === "disburse" ? "Jurnal Titipan biaya / Kas. Tidak boleh melebihi sisa titipan."
                  : "Tagihan AP ke notaris/BPN → jurnal Beban penjualan / Utang usaha."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Nominal (Rp)</Label>
            <RupiahInput data-testid={P75.costPayAmount} className="bg-background" value={form.amount || ""} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} />
            {view?.kind !== "pay" ? (<>
              <Label>{view?.kind === "disburse" ? "Penerima (notaris/BPN)" : "Vendor (notaris/BPN)"}</Label>
              <Input data-testid={P75.costPayee} className="bg-background" value={form.payee || ""} onChange={(e) => setForm((f) => ({ ...f, payee: e.target.value }))} />
            </>) : null}
            <Label htmlFor="cost-note">Catatan</Label>
            <Textarea id="cost-note" data-testid={P75.costNote} rows={2} className="bg-background" value={form.note || ""} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlg(null)}>Batal</Button>
            <Button data-testid={view?.kind === "pay" ? P75.costPaySubmit : view?.kind === "disburse" ? P75.costDisburseSubmit : P75.costExpenseSubmit} disabled={busy}
              onClick={view?.kind === "pay" ? pay : view?.kind === "disburse" ? disburse : expense}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
