import React, { useState } from "react";
import { PencilLine } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * ReviseDialog — revisi rencana anggaran, **wajib beralasan**.
 *
 * Kenapa revisi tidak sekadar mengubah angka di form biasa: begitu item anggaran menjadi
 * overbudget, satu-satunya jalan yang sah adalah menaikkan anggaran DENGAN ALASAN (atau
 * change order). Kalau angka rencana bisa diubah diam-diam, laporan overbudget bisa
 * “dibersihkan” tanpa jejak — dan sejak itu laporan itu tidak lagi berguna.
 */
export default function ReviseDialog({ item, open, onOpenChange, onDone }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!Number(amount)) { toast.error("Isi nilai anggaran baru."); return; }
    if (reason.trim().length < 5) { toast.error("Tulis alasan revisi (minimal 5 huruf)."); return; }
    setBusy(true);
    try {
      await api.post(`/budget/items/${item.id}/revise`, {
        planned_amount: Math.round(Number(amount)), reason: reason.trim(),
      });
      toast.success("Anggaran direvisi — jejaknya tersimpan permanen.");
      setAmount(""); setReason("");
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal merevisi anggaran.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUDGET.reviseDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Revisi anggaran — {item?.code}</DialogTitle>
          <DialogDescription>
            Rencana sekarang {formatIDR(item?.planned)} · exposure {formatIDR(item?.exposure)}.
            Revisi wajib beralasan dan tercatat di riwayat item.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="rev-amount">Rencana anggaran baru (Rp)</Label>
            <RupiahInput id="rev-amount" data-testid={BUDGET.reviseAmount}
              value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rev-reason">Alasan revisi</Label>
            <Textarea id="rev-reason" rows={3} data-testid={BUDGET.reviseReason}
              value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="mis. Tambahan pekerjaan drainase disetujui direksi (CO-002)" />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" disabled={busy} data-testid={BUDGET.reviseSubmit} onClick={submit}>
            <PencilLine className="mr-1.5 h-4 w-4" /> Simpan revisi
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
