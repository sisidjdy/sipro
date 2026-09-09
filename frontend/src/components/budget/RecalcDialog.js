import React, { useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * RecalcDialog — hitung ulang target secara manual, **wajib beralasan**.
 *
 * Alasan wajib bukan formalitas: penyesuaian target mengubah rencana bulan berjalan, dan
 * tanpa alasan tercatat, "kenapa target saya naik?" tidak akan pernah punya jawaban. Alasan
 * ini masuk `history[]` bersama daftar bulan yang berubah (sebelum → sesudah).
 */
export default function RecalcDialog({ target, open, onOpenChange, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (reason.trim().length < 5) {
      toast.error("Tulis alasan hitung ulang (minimal 5 huruf).");
      return;
    }
    setBusy(true);
    try {
      const r = await api.post(`/targets/${target.id}/recalc`, { reason: reason.trim() });
      const changed = (r.data?.data?.changes || []).length;
      toast.success(changed
        ? `Target dihitung ulang — ${changed} bulan berubah (jejaknya tercatat).`
        : "Target dihitung ulang — tidak ada bulan yang perlu berubah.");
      setReason("");
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghitung ulang target.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUDGET.recalcDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Hitung ulang target</DialogTitle>
          <DialogDescription>
            Periode lampau tetap dikunci (laporan historis tidak berubah). Kekurangan bulan
            lalu akan terlihat sebagai “dipindahkan” pada bulan berjalan.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="recalc-reason">Alasan hitung ulang</Label>
          <Textarea id="recalc-reason" data-testid={BUDGET.recalcReason} rows={3}
            value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="mis. Penyesuaian setelah launching cluster baru" />
        </div>
        <DialogFooter>
          <Button type="button" disabled={busy} data-testid={BUDGET.recalcSubmit} onClick={submit}>
            <RefreshCw className="mr-1.5 h-4 w-4" /> Hitung ulang
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
