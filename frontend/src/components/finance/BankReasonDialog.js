import React, { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

/**
 * BankReasonDialog — satu dialog untuk aksi yang WAJIB beralasan (batalkan pencocokan &
 * abaikan mutasi).
 *
 * Kenapa alasan diwajibkan di layar, bukan hanya di server: pembatalan pencocokan MEMBALIK
 * pembukuan yang sudah dilaporkan, dan mutasi yang “diabaikan” berarti perusahaan menyatakan
 * uang itu bukan urusannya. Keduanya harus bisa dipertanggungjawabkan oleh nama + alasan,
 * bukan sekadar klik.
 */
export default function BankReasonDialog({
  open, onOpenChange, title, description, confirmLabel, placeholder, minLength = 5,
  onSubmit, testIds = {},
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const short = reason.trim().length < minLength;

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit(reason.trim());
      setReason("");
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal diproses.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setReason(""); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="bank-reason-input">Alasan (wajib, minimal {minLength} huruf)</Label>
          <Textarea id="bank-reason-input" rows={3} value={reason} placeholder={placeholder}
            data-testid={testIds.reason} onChange={(e) => setReason(e.target.value)} />
          {short && reason.length ? (
            <p className="text-xs text-rose-600">
              Alasan masih terlalu pendek untuk bisa dibaca orang lain.
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={testIds.submit} disabled={busy || short} onClick={submit}>
            {busy ? "Memproses…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
