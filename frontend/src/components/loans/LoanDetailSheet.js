import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { HandCoins } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import PayInstallmentDialog from "@/components/loans/PayInstallmentDialog";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LOANS } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}

/** Detail fasilitas: pencairan (draf), jadwal angsuran, dan pembayaran angsuran. */
export default function LoanDetailSheet({ loanId, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState("bank");
  const [activating, setActivating] = useState(false);
  const [pay, setPay] = useState(null);

  const load = useCallback(async () => {
    if (!loanId) return;
    setLoading(true); setError("");
    try {
      const res = await api.get(`/corp-financing/loans/${loanId}`);
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat detail fasilitas.");
    } finally { setLoading(false); }
  }, [loanId]);

  useEffect(() => { load(); }, [load]);

  if (!loanId) return null;
  const l = data?.data;
  const schedule = l?.status === "draft" ? (data?.schedule_preview || []) : (l?.schedule || []);
  const principalTotal = schedule.reduce((s, r) => s + Number(r.principal || 0), 0);

  const activate = async () => {
    setActivating(true);
    try {
      await api.post(`/corp-financing/loans/${loanId}/activate`, { source, note: null });
      toast.success("Fasilitas dicairkan — jadwal angsuran diterbitkan & dibukukan.");
      await load(); onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencairkan fasilitas.");
    } finally { setActivating(false); }
  };

  return (
    <Sheet open onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent data-testid={LOANS.detailSheet} className="w-full overflow-y-auto sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {l ? `${l.no} — ${l.lender}` : "Detail Fasilitas"}
            {l ? <StatusPill status={l.status} group="loan_status" /> : null}
          </SheetTitle>
          <SheetDescription>
            Jadwal angsuran memisahkan pokok (mengurangi utang) dan bunga (beban).
          </SheetDescription>
        </SheetHeader>

        {loading ? <LoadingCards count={2} /> : error ? <ErrorState message={error} onRetry={load} /> : l ? (
          <div className="mt-4 space-y-4">
            <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <Row label="Jenis fasilitas" value={<RefLabel group="loan_type" value={l.loan_type} />} />
              <Row label="Jenis pemberi pinjaman" value={<RefLabel group="lender_type" value={l.lender_type} />} />
              <Row label="Metode amortisasi" value={<RefLabel group="amortization_method" value={l.amortization_method} />} />
              <Row label="Pokok pinjaman" value={formatIDR(l.principal)} />
              <Row label="Bunga" value={`${l.interest_rate_pct}% per tahun`} />
              <Row label="Tenor" value={`${l.tenor_months} bulan`} />
              <Row label="Biaya provisi" value={formatIDR(l.provision_fee)} />
              <Row label="Tanggal mulai" value={formatDateWIB(l.start_date)} />
              <Row label="Agunan" value={l.collateral || "—"} />
              {l.status !== "draft" ? (
                <>
                  <Row label="Sisa pokok" value={formatIDR(l.outstanding_principal)} />
                  <Row label="Pokok terbayar" value={formatIDR(l.paid_principal)} />
                  <Row label="Bunga terbayar" value={formatIDR(l.paid_interest)} />
                  <Row label="Angsuran lunas"
                    value={`${data.metrics?.installments_paid || 0} / ${data.metrics?.installments_total || 0}`} />
                </>
              ) : null}
            </div>

            {l.status === "draft" ? (
              <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm text-amber-900">
                  Fasilitas masih draf. Saat dicairkan: Dr kas/bank {formatIDR(l.principal - (l.provision_fee || 0))}
                  {l.provision_fee ? ` + Dr 6-1600 provisi ${formatIDR(l.provision_fee)}` : ""} / Cr 2-2100 {formatIDR(l.principal)}.
                </p>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-48 space-y-1">
                    <Label>Kas penerimaan</Label>
                    <ReferenceSelect group="cash_source" value={source} onChange={setSource}
                      testId={LOANS.activateSource} />
                  </div>
                  <Button data-testid={LOANS.activateSubmit} disabled={activating} onClick={activate}>
                    <HandCoins className="mr-1.5 h-4 w-4" />
                    {activating ? "Memproses…" : "Cairkan & Terbitkan Jadwal"}
                  </Button>
                </div>
              </div>
            ) : null}

            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase text-muted-foreground">
                  {l.status === "draft" ? "Pratinjau jadwal angsuran" : "Jadwal angsuran"}
                </p>
                <p data-testid={LOANS.scheduleTotal} className="text-xs text-muted-foreground">
                  Σ pokok jadwal: <span className="font-semibold tabular-nums">{formatIDR(principalTotal)}</span>
                </p>
              </div>
              <div className="max-h-96 overflow-y-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Jatuh Tempo</TableHead>
                      <TableHead className="text-right">Pokok</TableHead>
                      <TableHead className="text-right">Bunga</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead className="text-right">Terbayar</TableHead>
                      <TableHead>Status</TableHead>
                      {l.status === "active" ? <TableHead className="col-actions-head text-right">Aksi</TableHead> : null}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {schedule.map((r) => (
                      <TableRow key={r.no} data-testid={LOANS.scheduleRow} data-status={r.status}>
                        <TableCell className="font-medium">{r.no}</TableCell>
                        <TableCell className="text-sm">{formatDateWIB(r.due_date)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatIDR(r.principal)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatIDR(r.interest)}</TableCell>
                        <TableCell className="text-right font-medium tabular-nums">{formatIDR(r.total)}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {formatIDR(r.paid_total)}
                        </TableCell>
                        <TableCell>
                          <StatusPill status={r.status} group="installment_status" />
                        </TableCell>
                        {l.status === "active" ? (
                          <TableCell className="col-actions text-right">
                            {r.status !== "paid" ? (
                              <Button size="sm" data-testid={LOANS.payBtn}
                                onClick={() => setPay({ loan: l, item: r })}>Bayar</Button>
                            ) : null}
                          </TableCell>
                        ) : null}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            {(data.payments || []).length ? (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                  Riwayat pembayaran ({data.payments.length})
                </p>
                <div className="max-h-64 overflow-y-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Angsuran</TableHead>
                        <TableHead>Tanggal</TableHead>
                        <TableHead>Jurnal</TableHead>
                        <TableHead className="text-right">Pokok</TableHead>
                        <TableHead className="text-right">Bunga</TableHead>
                        <TableHead className="text-right">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.payments.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell>ke-{p.installment_no}</TableCell>
                          <TableCell className="text-sm">{formatDateWIB(p.paid_at)}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{p.entry_no}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(p.principal_part)}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(p.interest_part)}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(p.amount)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        <PayInstallmentDialog data={pay} onClose={() => setPay(null)}
          onSaved={async () => { await load(); onChanged?.(); }} />
      </SheetContent>
    </Sheet>
  );
}
