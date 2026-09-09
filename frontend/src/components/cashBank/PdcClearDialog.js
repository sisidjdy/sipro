import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PDC } from "@/constants/testIds";

/** Kliring giro: pilih rekening bank penerima → memorandum dibalik, uang masuk & kwitansi terbit. */
export default function PdcClearDialog({ open, pdc, onClose, onSaved }) {
  const [account, setAccount] = useState("");
  const [date, setDate] = useState("");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (open) { setAccount(""); setDate(new Date().toISOString().slice(0, 10)); setErr(""); } }, [open]);

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      const r = await api.post(`/pdc/${pdc.id}/clear`, { cash_account_id: account, cleared_date: date || null });
      const d = r.data.data;
      toast.success(`${d.no} cair ke ${d.cash_account_name}${d.receipt_no ? ` → kwitansi ${d.receipt_no}` : ""}.`);
      onSaved?.(); onClose();
    } catch (e) { setErr(e?.response?.data?.detail || "Gagal mengkliring giro."); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid={PDC.clearDialog}>
        <DialogHeader>
          <DialogTitle>Kliring {pdc?.kind_label} {pdc?.no}</DialogTitle>
          <DialogDescription>
            {formatIDR(pdc?.amount || 0)} dari {pdc?.issuer_name}{pdc?.unit_code ? ` · unit ${pdc.unit_code}` : ""}.
            {pdc?.deal_id ? " Uang dialokasikan ke termin & kwitansi KWT terbit." : " Tanpa deal — masuk sebagai titipan pelanggan."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <CashAccountSelect label="Rekening bank penerima" kind="bank" value={account} onChange={setAccount} testId={PDC.clearAccount} />
          <div className="space-y-1.5">
            <Label className="text-xs">Tanggal kliring</Label>
            <Input type="date" value={date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} className="h-9" data-testid={PDC.clearDate} />
          </div>
          {err ? <p className="text-sm text-rose-600" data-testid={PDC.error}>{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving || !account} data-testid={PDC.clearSubmit}>{saving ? "Memproses…" : "Cairkan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
