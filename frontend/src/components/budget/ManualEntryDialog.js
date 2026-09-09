import React, { useState } from "react";
import { NotebookPen } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * ManualEntryDialog — catat realisasi biaya yang benar-benar TERJADI DI LUAR SISTEM
 * (mis. kuitansi sewa direksi keet yang dibayar tunai tanpa PO/kas bon).
 *
 * Hanya tersedia untuk item ber-aturan “Dicatat manual”. Pada item yang dicocokkan otomatis,
 * server MENOLAK pencatatan manual — kalau diizinkan, biaya yang sama akan terhitung dua kali
 * (sekali dari dokumen, sekali dari ketikan). Setiap entri menyimpan pencatat + keterangan,
 * jadi lapis 3 tetap punya asal-usul.
 */
export default function ManualEntryDialog({ item, open, onOpenChange, onDone }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!Number(amount)) { toast.error("Isi nilai realisasi."); return; }
    if (note.trim().length < 5) { toast.error("Tulis keterangan (minimal 5 huruf)."); return; }
    setBusy(true);
    try {
      await api.post(`/budget/items/${item.id}/manual-entry`, {
        amount: Math.round(Number(amount)), note: note.trim(), kind: "realisasi",
        ref_no: ref.trim() || null,
      });
      toast.success("Realisasi manual tercatat.");
      setAmount(""); setNote(""); setRef("");
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencatat realisasi.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUDGET.manualDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Catat realisasi manual — {item?.code}</DialogTitle>
          <DialogDescription>
            Untuk biaya yang dibayar di luar sistem. Setiap entri wajib punya keterangan supaya
            angkanya tetap bisa ditelusuri saat diaudit.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="me-amount">Nilai realisasi (Rp)</Label>
            <RupiahInput id="me-amount" data-testid={BUDGET.manualAmount}
              value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="me-ref">Nomor bukti</Label>
            <Input id="me-ref" value={ref} onChange={(e) => setRef(e.target.value)}
              placeholder="mis. KWT/DK/2026/07" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="me-note">Keterangan</Label>
            <Textarea id="me-note" rows={3} data-testid={BUDGET.manualNote} value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="mis. Sewa direksi keet Jul-Ags 2026 (tunai, kuitansi manual)" />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" disabled={busy} data-testid={BUDGET.manualSubmit} onClick={submit}>
            <NotebookPen className="mr-1.5 h-4 w-4" /> Catat realisasi
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
