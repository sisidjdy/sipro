import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { DATAMGMT } from "@/constants/testIds";
import { errDetail } from "./dataMgmtUtils";

/** Dialog restore: pilih mode + ketik RESTORE. `submit(formData)` → promise axios. */
export default function RestoreDialog({ open, onOpenChange, title, submit, onDone }) {
  const [mode, setMode] = useState("replace");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => { if (open) { setConfirm(""); setResult(null); setMode("replace"); } }, [open]);

  const run = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("mode", mode); fd.append("confirm", confirm);
      const res = await submit(fd);
      setResult(res.data);
      toast.success(`Restore selesai: ${res.data.documents} dokumen.`);
      onDone?.();
    } catch (e) { toast.error(errDetail(e, "Restore gagal.")); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={DATAMGMT.restoreDialog} className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-rose-600" /> {title}</DialogTitle>
          <DialogDescription>
            Snapshot pengaman dibuat otomatis sebelum restore, dan akun Anda tidak akan hilang.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div data-testid={DATAMGMT.restoreResult} className="rounded-lg bg-emerald-50 text-emerald-900 p-3 text-sm space-y-1">
            <p><b>{result.documents}</b> dokumen dipulihkan pada {Object.keys(result.collections).filter((k) => !k.startsWith("_")).length} koleksi (mode {result.mode}).</p>
            <p className="text-xs">Snapshot pengaman: {result.snapshot_before?.label} · {result.snapshot_before?.documents} dokumen.</p>
            {result.collections._warnings?.map((w, i) => <p key={i} className="text-xs text-amber-800">{w}</p>)}
          </div>
        ) : (
          <div className="space-y-4">
            <RadioGroup data-testid={DATAMGMT.restoreMode} value={mode} onValueChange={setMode} className="gap-3">
              <label className="flex items-start gap-3 rounded-lg border p-3 cursor-pointer has-[:checked]:border-primary">
                <RadioGroupItem value="replace" id="rm-replace" className="mt-0.5" />
                <span><Label htmlFor="rm-replace" className="font-semibold">Ganti seluruhnya (replace)</Label>
                  <p className="text-xs text-muted-foreground">Data organisasi saat ini pada koleksi yang ada di backup dihapus, lalu diisi dari backup. Hasil = persis seperti saat backup.</p></span>
              </label>
              <label className="flex items-start gap-3 rounded-lg border p-3 cursor-pointer has-[:checked]:border-primary">
                <RadioGroupItem value="merge" id="rm-merge" className="mt-0.5" />
                <span><Label htmlFor="rm-merge" className="font-semibold">Gabungkan (merge)</Label>
                  <p className="text-xs text-muted-foreground">Dokumen dari backup ditimpa/ditambahkan berdasarkan ID; data lain yang sudah ada dibiarkan.</p></span>
              </label>
            </RadioGroup>
            <div className="space-y-1">
              <Label htmlFor="restore-confirm" className="text-xs">Ketik <b>RESTORE</b> untuk melanjutkan</Label>
              <Input id="restore-confirm" data-testid={DATAMGMT.restoreConfirm} value={confirm}
                onChange={(e) => setConfirm(e.target.value)} placeholder="RESTORE" autoComplete="off" />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{result ? "Tutup" : "Batal"}</Button>
          {!result ? (
            <Button variant="destructive" data-testid={DATAMGMT.restoreSubmit} disabled={busy || confirm.trim().toUpperCase() !== "RESTORE"}
              onClick={run}>{busy ? "Memulihkan…" : "Jalankan restore"}</Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
