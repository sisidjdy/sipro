import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

/**
 * Faktur PENGGANTI / PEMBATALAN (Fase 49E).
 *
 * Keduanya mengubah SPT Masa PPN, jadi alasan tertulis minimal 10 huruf diwajibkan di layar
 * DAN di backend. Faktur pengganti memakai nomor seri BARU dengan kode status pengganti,
 * sementara faktur lama tetap tersimpan dan menunjuk penggantinya (jejak dua arah).
 */
export default function FakturActionDialog({ mode, faktur, open, onOpenChange, onDone }) {
  const [reason, setReason] = useState("");
  const [npwp, setNpwp] = useState("");
  const [buyer, setBuyer] = useState("");
  const [dpp, setDpp] = useState("");
  const [busy, setBusy] = useState(false);
  const isReplace = mode === "replace";

  useEffect(() => {
    if (open) {
      setReason("");
      setNpwp(faktur?.buyer_npwp || "");
      setBuyer(faktur?.buyer_name || "");
      setDpp(faktur?.dpp ? String(faktur.dpp) : "");
    }
  }, [open, faktur]);

  const submit = async () => {
    if (!faktur?.id) return;
    setBusy(true);
    try {
      const url = `/tax/compliance/faktur/${faktur.id}/${isReplace ? "replace" : "cancel"}`;
      const body = isReplace
        ? {
          reason: reason.trim(),
          buyer_npwp: npwp.trim() || null,
          buyer_name: buyer.trim() || null,
          dpp: dpp ? Number(dpp) : null,
        }
        : { reason: reason.trim() };
      const res = await api.post(url, body);
      const doc = res.data.data || {};
      toast.success(isReplace
        ? `Faktur pengganti ${doc.number} terbit (menggantikan ${faktur.number}).`
        : `Faktur ${faktur.number} dibatalkan.`);
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail
        || (isReplace ? "Gagal menerbitkan faktur pengganti." : "Gagal membatalkan faktur."));
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P49.fakturActionDialog}>
        <DialogHeader>
          <DialogTitle>
            {isReplace ? `Terbitkan faktur pengganti untuk ${faktur?.number || ""}`
              : `Batalkan faktur ${faktur?.number || ""}`}
          </DialogTitle>
          <DialogDescription>
            {isReplace
              ? "Faktur pengganti memakai nomor seri baru berkode status pengganti; faktur lama tetap tersimpan dan menunjuk penggantinya."
              : "Faktur yang dibatalkan tidak lagi dihitung sebagai PPN keluaran, tetapi jumlahnya tetap terbaca di rekap SPT Masa PPN."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {isReplace ? (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="p49-faktur-buyer">Nama pembeli (boleh dikoreksi)</Label>
                <Input id="p49-faktur-buyer" value={buyer} onChange={(e) => setBuyer(e.target.value)}
                  placeholder="mis. Ibu Dewi Kartika" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="p49-faktur-npwp">NPWP pembeli</Label>
                  <Input id="p49-faktur-npwp" value={npwp} data-testid={P49.fakturActionNpwp}
                    onChange={(e) => setNpwp(e.target.value)} placeholder="16 digit (PMK 112/2022)" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="p49-faktur-dpp">DPP (Rp)</Label>
                  <RupiahInput id="p49-faktur-dpp" value={dpp} data-testid={P49.fakturActionDpp}
                    onChange={(e) => setDpp(e.target.value)} placeholder="0" />
                </div>
              </div>
            </>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="p49-faktur-reason">
              {isReplace ? "Alasan penggantian (≥10 huruf)" : "Alasan pembatalan (≥10 huruf)"}
            </Label>
            <Textarea id="p49-faktur-reason" rows={3} value={reason}
              data-testid={P49.fakturActionReason} onChange={(e) => setReason(e.target.value)}
              placeholder={isReplace
                ? "mis. NPWP pembeli salah ketik pada faktur lama"
                : "mis. Transaksi dibatalkan pembeli sebelum penyerahan unit"} />
            <p className="text-[11px] text-muted-foreground">{reason.trim().length}/10 huruf</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={busy} data-testid={P49.fakturActionCancel}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={P49.fakturActionSubmit} onClick={submit}
            variant={isReplace ? "default" : "destructive"}
            disabled={busy || reason.trim().length < 10}>
            {busy ? "Memproses…" : isReplace ? "Terbitkan pengganti" : "Batalkan faktur"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
