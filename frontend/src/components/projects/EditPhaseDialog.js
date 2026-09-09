import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import api from "@/services/apiClient";

/**
 * Ubah / hapus fase konstruksi (PUT & DELETE /construction/phases/{id}).
 * Sebelum audit hanya progres yang bisa diubah — nama/bobot salah tidak bisa dikoreksi
 * dan fase yang salah input tidak bisa dihapus.
 */
export default function EditPhaseDialog({ phase, open, onOpenChange, onDone }) {
  const [name, setName] = useState("");
  const [weight, setWeight] = useState("10");
  const [planned, setPlanned] = useState("0");
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (open && phase) {
      setName(phase.name || "");
      setWeight(String(phase.weight ?? 10));
      setPlanned(String(phase.planned_pct ?? 0));
    }
  }, [open, phase]);

  const save = async () => {
    if (!name.trim()) { toast.error("Nama fase wajib diisi."); return; }
    setBusy(true);
    try {
      const res = await api.put(`/construction/phases/${phase.id}`, {
        name, weight: Number(weight) || 0, planned_pct: Number(planned) || 0,
      });
      const synced = res.data?.denorm_synced || 0;
      toast.success(synced ? `Fase diperbarui. ${synced} dokumen terkait ikut disamakan.` : "Fase diperbarui.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui fase."); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.delete(`/construction/phases/${phase.id}`);
      toast.success(`Fase “${phase.name}” dihapus.`);
      setConfirmOpen(false);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus fase."); }
    finally { setBusy(false); }
  };

  const progress = Number(phase?.progress || 0);
  const deletable = progress === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ubah Fase Konstruksi</DialogTitle>
          <DialogDescription>
            Bobot menentukan kontribusi fase ke progres proyek. Nama baru ikut disamakan ke
            permintaan material terkait.
          </DialogDescription>
        </DialogHeader>
        <p data-testid="phase-edit-progress-info"
          className="rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          Progres fase saat ini: <b className="tabular-nums text-foreground">{progress}%</b>.{" "}
          {deletable
            ? "Karena progres masih 0%, fase ini boleh dihapus."
            : "Fase yang sudah punya progres tidak bisa dihapus — turunkan progres ke 0 lebih dulu."}
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="editphasedialog-nama-fase">Nama Fase</Label>
            <Input id="editphasedialog-nama-fase" data-testid="phase-edit-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="editphasedialog-bobot">Bobot (%)</Label>
            <Input id="editphasedialog-bobot" data-testid="phase-edit-weight" type="number" value={weight}
              onChange={(e) => setWeight(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="editphasedialog-rencana">Rencana (%)</Label>
            <Input id="editphasedialog-rencana" data-testid="phase-edit-planned" type="number" value={planned}
              onChange={(e) => setPlanned(e.target.value)} />
          </div>
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
          <Button data-testid="phase-delete-btn" variant="ghost" className="text-rose-700"
            disabled={busy || !deletable} onClick={() => setConfirmOpen(true)}
            aria-label={`Hapus fase ${phase?.name || ""}`}
            title={deletable ? "Hapus fase" : "Fase sudah punya progres — tidak bisa dihapus"}>
            Hapus fase
          </Button>
          <span className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
            <Button data-testid="phase-edit-submit" onClick={save} disabled={busy}>
              {busy ? "Menyimpan…" : "Simpan"}
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
      <ConfirmDialog open={confirmOpen} onOpenChange={setConfirmOpen}
        title={`Hapus fase “${phase?.name || ""}”?`}
        description="Bobot fase akan hilang dan progres proyek dihitung ulang. Tindakan ini tidak bisa dibatalkan."
        confirmLabel="Ya, hapus fase" busy={busy} onConfirm={remove}
        testId="phase-delete-confirm" />
    </Dialog>
  );
}
