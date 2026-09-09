import React, { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { P50 } from "@/constants/testIds";

const MIN_REASON = 10;

/**
 * Dialog penerbitan BAST (Fase 50A).
 *
 * Dua keadaan JUJUR dalam satu dialog:
 *  * daftar periksa bersih → cukup mengisi data serah terima (penerima, meter, kunci);
 *  * masih ada yang menahan → sebabnya ditulis apa adanya, dan penerbitan hanya boleh
 *    dilanjutkan oleh peran berwenang dengan ALASAN tertulis (≥ 10 huruf) yang akan
 *    melahirkan tugas tinjauan. Tanpa itu tombolnya tetap nonaktif.
 */
export default function HandoverIssueDialog({
  open, unitCode, blocking = [], canOverride, onOpenChange, onSubmit,
}) {
  const [form, setForm] = useState({ handed_over_at: "", received_by: "", meter_air: "",
    meter_listrik: "", keys_handed: "", note: "" });
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) {
      setForm({ handed_over_at: "", received_by: "", meter_air: "", meter_listrik: "",
        keys_handed: "", note: "" });
      setReason("");
    }
  }, [open]);

  const needOverride = blocking.length > 0;
  const reasonOk = reason.trim().length >= MIN_REASON;
  const blocked = needOverride && (!canOverride || !reasonOk);

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit({
        handed_over_at: form.handed_over_at || null,
        received_by: form.received_by.trim() || null,
        meter_air: form.meter_air.trim() || null,
        meter_listrik: form.meter_listrik.trim() || null,
        keys_handed: form.keys_handed === "" ? null : Number(form.keys_handed),
        note: form.note.trim() || null,
        override: needOverride,
        override_reason: needOverride ? reason.trim() : null,
      });
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P50.handoverIssueDialog}
        className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Serah terima rumah {unitCode}</DialogTitle>
          <DialogDescription>
            Tanggal serah terima menjadi titik mulai seluruh masa garansi, jadi isilah apa
            adanya.
          </DialogDescription>
        </DialogHeader>

        {needOverride ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-[13px] text-rose-900">
            <p className="font-semibold">
              {blocking.length} pemeriksaan masih menahan serah terima:
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {blocking.map((b) => <li key={b.code}>{b.detail}</li>)}
            </ul>
            <p className="mt-1.5">
              {canOverride
                ? "Melanjutkan berarti menerobos daftar periksa — tulis dasarnya, dan tugas tinjauan akan dibuat otomatis."
                : "Anda tidak punya kewenangan menerobos. Tuntaskan sebab di atas, atau mintakan persetujuan Manajer Keuangan/Direksi."}
            </p>
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="ho-date">Tanggal serah terima</Label>
            <Input id="ho-date" type="date" data-testid={P50.handoverIssueDate}
              value={form.handed_over_at}
              onChange={(e) => set("handed_over_at", e.target.value)} />
            <p className="text-[11px] text-muted-foreground">Kosongkan untuk hari ini.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ho-receiver">Diterima oleh</Label>
            <Input id="ho-receiver" data-testid={P50.handoverIssueReceiver}
              value={form.received_by} placeholder="Nama penerima kunci"
              onChange={(e) => set("received_by", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ho-water">Angka meter air</Label>
            <Input id="ho-water" data-testid={P50.handoverIssueWater} value={form.meter_air}
              onChange={(e) => set("meter_air", e.target.value)} placeholder="mis. 0124" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ho-elec">Angka meter listrik</Label>
            <Input id="ho-elec" data-testid={P50.handoverIssueElectric}
              value={form.meter_listrik} placeholder="mis. 8891"
              onChange={(e) => set("meter_listrik", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ho-keys">Jumlah kunci diserahkan</Label>
            <Input id="ho-keys" type="number" min={0} data-testid={P50.handoverIssueKeys}
              value={form.keys_handed}
              onChange={(e) => set("keys_handed", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="ho-note">Catatan (opsional)</Label>
            <Textarea id="ho-note" rows={2} data-testid={P50.handoverIssueNote}
              value={form.note} onChange={(e) => set("note", e.target.value)}
              placeholder="mis. kunci gerbang belakang menyusul minggu depan" />
          </div>
          {needOverride && canOverride ? (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="ho-reason">Alasan terobosan (minimal {MIN_REASON} huruf)</Label>
              <Textarea id="ho-reason" rows={3} data-testid={P50.handoverIssueReason}
                value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="mis. pembeli sudah menempati rumah atas persetujuan direksi" />
              <p className={`text-[11px] ${reasonOk ? "text-muted-foreground" : "text-rose-700"}`}>
                {reason.trim().length}/{MIN_REASON} huruf — alasan ini ikut tercetak di BAST
                dan menjadi tugas tinjauan.
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={busy} data-testid={P50.handoverIssueCancel}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={P50.handoverIssueSubmit} onClick={submit}
            disabled={busy || blocked}>
            {busy ? "Memproses…" : needOverride ? "Serahkan dengan terobosan" : "Terbitkan BAST"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
