import React, { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import RefLabel from "@/components/patterns/RefLabel";
import api from "@/services/apiClient";
import { changeText, newClientRef, rowShift, stamp } from "@/utils/calibrationUi";
import { CALIB } from "@/constants/testIds";

/**
 * BATALKAN KALIBRASI (Fase 37) — kembalikan template ke nilai SEBELUM kalibrasi itu, tepat.
 *
 * Backend menyimpan sebelum→sesudah setiap langkah yang tersentuh, jadi pembatalan bukan
 * kira-kira. Dua penjaga yang sengaja terasa di UI: (1) tetap wajib beralasan (minimal 10
 * karakter) karena pembatalan juga keputusan perencanaan, dan (2) bila template sudah
 * berubah lagi setelah kalibrasi ini, backend menolak dengan jujur dan menyuruh membatalkan
 * kalibrasi yang paling baru lebih dulu — supaya perubahan orang lain tidak terhapus.
 */
export default function CalibrationRollbackDialog({ open, onOpenChange, calibration, onDone }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ref, setRef] = useState(newClientRef());

  React.useEffect(() => {
    if (!open) return;
    setNote("");
    setError("");
    setRef(newClientRef());
  }, [open, calibration?.id]);

  const run = async () => {
    if (note.trim().length < 10) {
      toast.error("Catatan pembatalan minimal 10 karakter (jejak audit).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await api.post(`/build/calibration/${calibration.id}/rollback`,
        { note: note.trim(), client_ref: ref });
      toast.success(r.data?.message || "Kalibrasi dikembalikan ke nilai sebelumnya.");
      onDone && onDone();
      onOpenChange(false);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal membatalkan kalibrasi.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={CALIB.rbDialog}
        className="max-h-[92vh] overflow-y-auto bg-card sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5 text-primary" /> Batalkan kalibrasi
          </DialogTitle>
          <DialogDescription>
            Template dikembalikan TEPAT ke nilai sebelum kalibrasi ini. Jadwal rumah yang
            sudah dibuat tetap tidak tersentuh, dan pembatalannya ikut tercatat di riwayat.
          </DialogDescription>
        </DialogHeader>

        {calibration ? (
          <div className="space-y-1.5 rounded-xl border bg-background p-3 text-xs">
            <p className="font-medium">
              <span className="font-mono">{calibration.step_code || calibration.step || "—"}</span>{" "}
              {calibration.step_name || ""}
              {calibration.kind ? (
                <span className="ml-1.5 text-muted-foreground">
                  (<RefLabel group="calibration_kind" value={calibration.kind} />)
                </span>
              ) : null}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {calibration.template_code ? `Template ${calibration.template_code} · ` : ""}
              {changeText(calibration)} · diterapkan{" "}
              {stamp(calibration.at || calibration.created_at)} oleh{" "}
              {calibration.by || calibration.actor || "—"}
            </p>
            {calibration.note ? (
              <p className="rounded-lg border bg-secondary p-2 text-[11px] text-muted-foreground">
                Alasan semula: {calibration.note}
              </p>
            ) : null}
            {(calibration.rows || []).length ? (
              <div className="max-h-40 overflow-y-auto rounded-lg border">
                <table className="w-full text-[11px]">
                  <tbody>
                    {calibration.rows.map((r) => (
                      <tr key={r.code} className="border-b last:border-0">
                        <td className="px-2 py-1 font-mono">{r.code}</td>
                        <td className="px-2 py-1 tabular-nums">
                          {rowShift({ before: r.after, after: r.before })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="calib-rb-note">Alasan pembatalan (wajib)</Label>
          <Textarea id="calib-rb-note" rows={2} data-testid={CALIB.rbNote} value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Contoh: durasi ternyata cukup setelah regu tambahan dipakai, kembalikan ke angka semula." />
          <p className="text-[11px] text-muted-foreground">
            {note.trim().length}/10 karakter minimal
          </p>
        </div>

        {error ? (
          <p data-testid={CALIB.rbError}
            className="rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-800">
            <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />{error}
          </p>
        ) : null}

        {note.trim().length < 10 ? (
          <p data-testid={CALIB.rbHint}
            className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            Tulis alasan pembatalan minimal 10 karakter — riwayat kalibrasi dipakai untuk
            membaca pola keputusan perencanaan.
          </p>
        ) : null}

        <DialogFooter className="gap-2">
          <Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
            Tutup
          </Button>
          <Button variant="destructive" data-testid={CALIB.rbConfirm} onClick={run}
            disabled={busy || note.trim().length < 10}>
            {busy ? "Mengembalikan…" : "Kembalikan nilai semula"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
