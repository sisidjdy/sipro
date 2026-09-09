import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, XCircle } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LOCKS } from "@/constants/testIds";

function prevMonth() {
  const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 7);
}

/** Kunci satu periode untuk satu rekening/kas — pratinjau kelayakan dari server sebelum mengunci. */
export default function PeriodLockDialog({ open, account, onClose, onSaved }) {
  const [period, setPeriod] = useState(prevMonth());
  const [counted, setCounted] = useState("");
  const [note, setNote] = useState("");
  const [pv, setPv] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const isCash = account?.kind === "cash";

  useEffect(() => { if (open) { setPeriod(prevMonth()); setCounted(""); setNote(""); setPv(null); setErr(""); } }, [open, account]);

  useEffect(() => {
    if (!open || !account || period.length !== 7) return;
    const params = { account_id: account.account_id, period };
    if (isCash && counted !== "") params.counted_balance = Number(counted);
    api.get("/cash-bank/locks/preview", { params }).then((r) => { setPv(r.data.data); setErr(""); })
      .catch((e) => { setPv(null); setErr(e?.response?.data?.detail || "Gagal memuat pratinjau."); });
  }, [open, account, period, counted, isCash]);

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post("/cash-bank/locks", { account_id: account.account_id, period,
        counted_balance: isCash && counted !== "" ? Number(counted) : null, note: note || null });
      toast.success(`${account.name} dikunci s.d. ${period}.`);
      onSaved?.(); onClose();
    } catch (e) { setErr(e?.response?.data?.detail || "Gagal mengunci periode."); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg" data-testid={LOCKS.dialog}>
        <DialogHeader>
          <DialogTitle>Kunci Periode — {account?.name}</DialogTitle>
          <DialogDescription>Saldo penutup periode ini menjadi saldo awal tetap periode berikutnya.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Periode (bulan)</Label>
              <Input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="h-9" data-testid={LOCKS.period} />
            </div>
            {isCash ? (
              <div className="space-y-1.5">
                <Label className="text-xs">Hasil opname kas (fisik) akhir periode</Label>
                <RupiahInput value={counted} onChange={(e) => setCounted(e.target.value)} data-testid={LOCKS.counted} />
              </div>
            ) : null}
          </div>
          {pv ? (
            <div className={`rounded-lg border p-3 text-sm space-y-1 ${pv.eligible ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`} data-testid={LOCKS.preview}>
              <p className="flex items-center gap-2 font-medium" data-testid={LOCKS.previewStatus}>
                {pv.eligible ? <CheckCircle2 className="h-4 w-4 text-emerald-700" /> : <XCircle className="h-4 w-4 text-amber-700" />}
                {pv.eligible ? "Layak dikunci" : "Belum layak dikunci"}
              </p>
              <p>Saldo buku per {pv.period_end}: <b>{formatIDR(pv.closing_balance)}</b></p>
              {pv.recon ? (
                <p className="text-xs text-muted-foreground">Rekonsiliasi: {pv.recon.status} · saldo rekening {pv.recon.statement_balance != null ? formatIDR(pv.recon.statement_balance) : "—"} per {pv.recon.as_of}
                  {pv.recon.unmatched_count ? ` · ${pv.recon.unmatched_count} mutasi belum cocok` : ""}</p>
              ) : null}
              {pv.reasons.map((r, i) => <p key={i} className="text-xs text-amber-900">• {r}</p>)}
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label className="text-xs">Catatan (opsional)</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} className="h-9" placeholder="Mis. BA opname kas 31/08" />
          </div>
          {err ? <p className="text-sm text-rose-600" data-testid={LOCKS.error}>{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving || !pv?.eligible} data-testid={LOCKS.submit}>{saving ? "Mengunci…" : "Kunci periode"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
