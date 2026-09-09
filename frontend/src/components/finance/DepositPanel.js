import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { PiggyBank, Plus, ArrowRightLeft, Undo2, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { FINANCE } from "@/constants/testIds";

/**
 * Titipan Pelanggan (customer deposits) — Fase 26.
 *
 * Uang pembeli yang belum menjadi pembayaran termin: kelebihan bayar atau setoran di muka.
 * Dicatat sebagai KEWAJIBAN (akun 2-1450), bukan pendapatan; bisa dipakai untuk termin
 * berikutnya (2-1450 → 2-1400) atau dikembalikan (2-1450 → kas).
 */
export default function DepositPanel() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [ars, setArs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [action, setAction] = useState(null); // { kind: "apply"|"refund", row }
  const [history, setHistory] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [d, a] = await Promise.all([
        api.get("/finance/ar/deposits"),
        api.get("/finance/ar"),
      ]);
      setRows(d.data.data || []);
      setTotal(d.data.balance_total || 0);
      setArs(a.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data titipan pelanggan.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const outstandingOf = (dealId) =>
    Number((ars.find((x) => x.deal_id === dealId) || {}).outstanding || 0);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={FINANCE.depositPanel} className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Saldo Titipan Pelanggan" value={total} tone="indigo" format="idr"
          hint="Kewajiban akun 2-1450" />
        <MetricCard label="Pembeli dengan Titipan" value={rows.filter((r) => r.balance > 0).length}
          tone="primary" hint="Saldo masih tersedia" />
        <MetricCard label="Total Pernah Diterima"
          value={rows.reduce((s, r) => s + Number(r.received_total || 0), 0)} tone="emerald" format="idr" />
        <MetricCard label="Sudah Dipakai / Dikembalikan"
          value={rows.reduce((s, r) => s + Number(r.applied_total || 0) + Number(r.refunded_total || 0), 0)}
          tone="amber" format="idr" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Titipan tidak pernah diakui sebagai pendapatan. Setiap mutasi punya jurnal seimbang.
        </p>
        <Button data-testid={FINANCE.depositReceiveBtn} onClick={() => setReceiveOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Terima Titipan
        </Button>
      </div>

      {!rows.length ? (
        <EmptyState icon={PiggyBank} title="Belum ada titipan pelanggan"
          description="Titipan muncul saat pembeli membayar lebih dari sisa tagihan (dengan persetujuan kasir) atau menyetor di muka lewat tombol Terima Titipan." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Unit</TableHead>
                <TableHead>Pembeli</TableHead>
                <TableHead className="text-right">Saldo Titipan</TableHead>
                <TableHead className="text-right">Masuk</TableHead>
                <TableHead className="text-right">Dipakai</TableHead>
                <TableHead className="text-right">Dikembalikan</TableHead>
                <TableHead className="text-right">Sisa Tagihan</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.deal_id} data-testid={FINANCE.depositRow}>
                  <TableCell className="font-medium">{r.unit_code || "-"}</TableCell>
                  <TableCell>{r.customer_name || "-"}</TableCell>
                  <TableCell data-testid={FINANCE.depositBalance}
                    className="text-right font-semibold tabular-nums text-indigo-700">
                    {formatIDR(r.balance)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{formatIDR(r.received_total)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{formatIDR(r.applied_total)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{formatIDR(r.refunded_total)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(outstandingOf(r.deal_id))}</TableCell>
                  <TableCell className="col-actions">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="ghost" data-testid={FINANCE.depositHistoryBtn}
                        onClick={() => setHistory(r)}>
                        <History className="h-3.5 w-3.5" />
                      </Button>
                      {r.balance > 0 && outstandingOf(r.deal_id) > 0 ? (
                        <Button size="sm" data-testid={FINANCE.depositApplyBtn}
                          onClick={() => setAction({ kind: "apply", row: r })}>
                          <ArrowRightLeft className="mr-1 h-3.5 w-3.5" /> Gunakan
                        </Button>
                      ) : null}
                      {r.balance > 0 ? (
                        <Button size="sm" variant="outline" data-testid={FINANCE.depositRefundBtn}
                          onClick={() => setAction({ kind: "refund", row: r })}>
                          <Undo2 className="mr-1 h-3.5 w-3.5" /> Kembalikan
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

      <ReceiveDepositDialog open={receiveOpen} onOpenChange={setReceiveOpen} ars={ars} onDone={load} />
      <DepositActionDialog action={action} onOpenChange={(v) => !v && setAction(null)}
        maxApply={action ? Math.min(Number(action.row.balance || 0), outstandingOf(action.row.deal_id)) : 0}
        onDone={load} />
      <HistoryDialog row={history} onOpenChange={(v) => !v && setHistory(null)} />
    </div>
  );
}

function ReceiveDepositDialog({ open, onOpenChange, ars, onDone }) {
  const [dealId, setDealId] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setDealId(""); setAmount(""); setNote(""); } }, [open]);

  const submit = async () => {
    if (!dealId) { toast.error("Pilih deal/unit pembeli."); return; }
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error("Nominal titipan harus lebih dari 0."); return; }
    setBusy(true);
    try {
      await api.post(`/finance/ar/${dealId}/deposit`, { amount: amt, note: note || null });
      toast.success(`Titipan ${formatIDR(amt)} diterima (kewajiban 2-1450).`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mencatat titipan."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Terima Titipan Pelanggan</DialogTitle>
          <DialogDescription>
            Setoran di muka yang belum dialokasikan ke termin — dicatat sebagai kewajiban, bukan pendapatan.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Deal / Unit</Label>
            <Select value={dealId} onValueChange={setDealId}>
              <SelectTrigger data-testid={FINANCE.depositDealSelect}>
                <SelectValue placeholder="Pilih unit pembeli" />
              </SelectTrigger>
              <SelectContent>
                {ars.map((a) => (
                  <SelectItem key={a.deal_id} value={a.deal_id}>
                    {a.unit_code || "Unit"} · {a.lead_name || "Pembeli"} · sisa {formatIDR(a.outstanding)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="depamt">Nominal (Rp)</Label>
            <RupiahInput id="depamt" value={amount} data-testid={FINANCE.depositAmount}
              onChange={(e) => setAmount(e.target.value)} placeholder="0" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="depnote">Catatan (opsional)</Label>
            <Textarea id="depnote" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="mis. setoran awal menunggu jadwal termin" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FINANCE.depositReceiveSubmit} onClick={submit} disabled={busy}>
            {busy ? "Memproses…" : "Simpan Titipan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DepositActionDialog({ action, onOpenChange, maxApply, onDone }) {
  const kind = action?.kind;
  const row = action?.row;
  const isApply = kind === "apply";
  const max = isApply ? maxApply : Number(row?.balance || 0);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (action) { setAmount(String(max || "")); setNote(""); } }, [action, max]);

  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error("Nominal harus lebih dari 0."); return; }
    setBusy(true);
    try {
      // Path ditulis eksplisit (bukan disusun dari variabel) agar kontrak API tetap
      // bisa diverifikasi otomatis oleh gate verify_api_contract.
      const url = isApply
        ? `/finance/ar/${row.deal_id}/deposit/apply`
        : `/finance/ar/${row.deal_id}/deposit/refund`;
      await api.post(url, { amount: amt, note: note || null });
      toast.success(isApply
        ? `${formatIDR(amt)} titipan dipakai untuk termin.`
        : `${formatIDR(amt)} titipan dikembalikan ke pelanggan.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Aksi titipan gagal."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={!!action} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isApply ? "Gunakan Titipan untuk Termin" : "Kembalikan Titipan"}</DialogTitle>
          <DialogDescription>
            {row ? `${row.unit_code || "Unit"} · saldo titipan ${formatIDR(row.balance)}` : ""}
            {isApply ? ` · maksimal ${formatIDR(max)} (batas sisa tagihan)` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="actamt">Nominal (Rp)</Label>
            <RupiahInput id="actamt" value={amount}
              data-testid={FINANCE.depositActionAmount}
              onChange={(e) => setAmount(e.target.value)} />
            {Number(amount) > max ? (
              <p data-testid={FINANCE.depositActionWarning} className="text-[12px] font-medium text-rose-700">
                Melebihi batas {formatIDR(max)} — backend akan menolak demi menjaga pembukuan.
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="actnote">Catatan (opsional)</Label>
            <Textarea id="actnote" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <p className="rounded-lg bg-secondary p-2.5 text-[12px] text-muted-foreground">
            {isApply
              ? "Jurnal: Dr 2-1450 Titipan Pelanggan / Cr 2-1400 Uang Muka — tidak ada kas baru masuk."
              : "Jurnal: Dr 2-1450 Titipan Pelanggan / Cr 1-1200 Bank — kas keluar."}
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FINANCE.depositActionSubmit} onClick={submit} disabled={busy}>
            {busy ? "Memproses…" : isApply ? "Gunakan" : "Kembalikan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function HistoryDialog({ row, onOpenChange }) {
  return (
    <Dialog open={!!row} onOpenChange={onOpenChange}>
      <DialogContent data-testid={FINANCE.depositHistory}>
        <DialogHeader>
          <DialogTitle>Riwayat Mutasi Titipan</DialogTitle>
          <DialogDescription>{row ? `${row.unit_code || "Unit"} · ${row.customer_name || ""}` : ""}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[50vh] space-y-2 overflow-y-auto">
          {!(row?.entries || []).length ? (
            <p className="text-sm text-muted-foreground">Belum ada mutasi.</p>
          ) : (row.entries || []).slice().reverse().map((e) => (
            <div key={e.id} className="flex items-center justify-between rounded-lg border bg-card p-2.5 text-sm shadow-[var(--shadow-card)]">
              <div>
                <p className="font-medium"><RefLabel group="deposit_txn" value={e.type} /></p>
                <p className="text-[11px] text-muted-foreground">{formatDateWIB(e.created_at)} · {e.note || "-"}</p>
              </div>
              <span className={`tabular-nums font-semibold ${e.type === "in" ? "text-emerald-700" : "text-amber-700"}`}>
                {e.type === "in" ? "+" : "−"}{formatIDR(e.amount)}
              </span>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
