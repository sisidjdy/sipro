import React, { useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { LEADS } from "@/constants/testIds";

/**
 * AssignLeadsDialog — aksi MASSAL “tugaskan ulang” untuk beberapa lead sekaligus (US-40-1).
 *
 * Kejujuran hasil: penugasan dikirim satu-per-satu ke endpoint yang sudah ada
 * (`POST /leads/{id}/assign`) dan yang dilaporkan ke pemakai adalah jumlah yang BENAR-BENAR
 * berhasil beserta jumlah yang gagal — bukan “berhasil” selimut.
 */
export default function AssignLeadsDialog({ open, onOpenChange, rows = [], owners = [], onDone }) {
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!target) { toast.error("Pilih PIC tujuan."); return; }
    setBusy(true);
    let ok = 0;
    const failed = [];
    for (const row of rows) {
      try {
        // eslint-disable-next-line no-await-in-loop
        await api.post(`/leads/${row.id}/assign`, { assigned_to: target });
        ok += 1;
      } catch (e) {
        failed.push(`${row.name}: ${e?.response?.data?.detail || "gagal"}`);
      }
    }
    setBusy(false);
    if (ok) toast.success(`${ok} lead dipindahkan ke ${target}.`);
    if (failed.length) toast.error(`${failed.length} gagal — ${failed[0]}`);
    onOpenChange(false);
    setTarget("");
    onDone?.();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-background">
        <DialogHeader>
          <DialogTitle>Tugaskan {rows.length} lead ke PIC lain</DialogTitle>
          <DialogDescription>
            Setiap perpindahan tercatat pada riwayat lead masing-masing.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="assign-target">PIC tujuan</Label>
          <Select value={target} onValueChange={setTarget}>
            <SelectTrigger id="assign-target" data-testid={LEADS.bulkAssignTarget}
              aria-label="PIC tujuan">
              <SelectValue placeholder="Pilih sales…" />
            </SelectTrigger>
            <SelectContent>
              {owners.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Pilihan diambil dari PIC yang sudah memegang lead pada cakupan Anda.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={LEADS.bulkAssignSubmit} onClick={submit} disabled={busy || !target}>
            {busy ? "Memindahkan…" : `Tugaskan ${rows.length} lead`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
