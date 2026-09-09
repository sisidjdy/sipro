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
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

/**
 * PEMBETULAN / PEMBATALAN bukti potong (Fase 49F).
 *
 * PER-24/PJ/2021: pembetulan TIDAK mengubah nomor bukti — versinya naik dan nilai lama
 * tersimpan sebagai riwayat, karena pihak yang dipotong sudah memegang nomor itu. Bukti yang
 * dibatalkan tidak boleh dipakai lagi; bila potongannya memang terjadi, terbitkan bukti baru.
 */
export default function WithholdingActionDialog({ mode, doc, open, onOpenChange, onDone }) {
  const [reason, setReason] = useState("");
  const [base, setBase] = useState("");
  const [rate, setRate] = useState("");
  const [npwp, setNpwp] = useState("");
  const [objectCode, setObjectCode] = useState("");
  const [busy, setBusy] = useState(false);
  const isCorrect = mode === "correct";

  useEffect(() => {
    if (!open) return;
    setReason("");
    setBase(doc?.base ? String(doc.base) : "");
    setRate(doc?.rate ? String(doc.rate) : "");
    setNpwp(doc?.party_npwp || "");
    setObjectCode(doc?.object_code || "");
  }, [open, doc]);

  const submit = async () => {
    if (!doc?.id) return;
    setBusy(true);
    try {
      const url = `/tax/compliance/withholding/${doc.id}/${isCorrect ? "correct" : "cancel"}`;
      const body = isCorrect
        ? {
          reason: reason.trim(),
          base: base ? Number(base) : null,
          rate: rate ? Number(rate) : null,
          party_npwp: npwp.trim() || null,
          object_code: objectCode.trim() || null,
        }
        : { reason: reason.trim() };
      const res = await api.post(url, body);
      const updated = res.data.data || {};
      toast.success(isCorrect
        ? `Bukti potong ${updated.number} dibetulkan (versi ${updated.version}, nomor tetap).`
        : `Bukti potong ${doc.number} dibatalkan.`);
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail
        || (isCorrect ? "Gagal membetulkan bukti potong." : "Gagal membatalkan bukti potong."));
    } finally { setBusy(false); }
  };

  const amount = Math.round((Number(base) || 0) * (Number(rate) || 0) / 100);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P49.bupotActionDialog} className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isCorrect ? `Betulkan bukti potong ${doc?.number || ""}`
              : `Batalkan bukti potong ${doc?.number || ""}`}
          </DialogTitle>
          <DialogDescription>
            {isCorrect
              ? "Nomor bukti TIDAK berubah (PER-24/PJ/2021); versinya naik dan nilai lama tersimpan sebagai riwayat."
              : "Nomor bukti yang dibatalkan tidak boleh dipakai lagi. Bila potongannya memang terjadi, terbitkan bukti baru."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {isCorrect ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="p49-bupot-cbase">Dasar pengenaan (Rp)</Label>
                  <RupiahInput id="p49-bupot-cbase" value={base}
                    data-testid={P49.bupotActionBase} onChange={(e) => setBase(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="p49-bupot-crate">Tarif (%)</Label>
                  <Input id="p49-bupot-crate" type="number" step="0.01" value={rate}
                    data-testid={P49.bupotActionRate} onChange={(e) => setRate(e.target.value)} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="p49-bupot-cnpwp">NPWP/NIK pihak dipotong</Label>
                <Input id="p49-bupot-cnpwp" value={npwp} onChange={(e) => setNpwp(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>Kode objek pajak</Label>
                <ReferenceSelect group="withholding_object_code" value={objectCode}
                  onChange={setObjectCode} allowEmpty emptyLabel="— belum ada kode —"
                  testId="p49-bupot-action-object" />
              </div>
              <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
                Nilai potongan setelah pembetulan: {" "}
                <span className="font-semibold tabular-nums">{formatIDR(amount)}</span>
                {" "}(sebelumnya {formatIDR(doc?.amount)}). Selisihnya akan tampil sebagai
                “belum berbukti potong” bila potongan nyatanya berbeda.
              </div>
            </>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="p49-bupot-reason">
              {isCorrect ? "Alasan pembetulan (≥10 huruf)" : "Alasan pembatalan (≥10 huruf)"}
            </Label>
            <Textarea id="p49-bupot-reason" rows={3} value={reason}
              data-testid={P49.bupotActionReason} onChange={(e) => setReason(e.target.value)}
              placeholder={isCorrect
                ? "mis. Dasar pengenaan salah karena nilai jasa dihitung termasuk material"
                : "mis. Pembayaran dibatalkan bank sehingga potongan tidak pernah terjadi"} />
            <p className="text-[11px] text-muted-foreground">{reason.trim().length}/10 huruf</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={busy} data-testid={P49.bupotActionCancel}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={P49.bupotActionSubmit} onClick={submit}
            variant={isCorrect ? "default" : "destructive"}
            disabled={busy || reason.trim().length < 10}>
            {busy ? "Memproses…" : isCorrect ? "Betulkan (nomor tetap)" : "Batalkan bukti potong"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
