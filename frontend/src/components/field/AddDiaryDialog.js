import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import PhotoUploader from "@/components/patterns/PhotoUploader";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import * as sync from "@/services/offlineSync";
import { FIELD } from "@/constants/testIds";

const EMPTY = { log_date: "", weather: "", workforce: "", work_description: "", materials: "", equipment: "", obstacles: "" };

export default function AddDiaryDialog({ projectId, open, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  useEffect(() => { if (open) { setForm(EMPTY); setPhotos([]); } }, [open]);

  const submit = async () => {
    if (!form.work_description.trim()) { toast.error("Isi uraian pekerjaan."); return; }
    setBusy(true);
    try {
      // Fase 50B: buku harian ditulis di lokasi. Bila sinyal mati (atau fotonya masih
      // tersimpan di perangkat), catatan MASUK ANTREAN dan terkirim sendiri nanti.
      const out = await sync.submitOrQueue({
        kind: "field_diary",
        payload: {
          project_id: projectId,
          log_date: form.log_date ? new Date(form.log_date).toISOString() : null,
          weather: form.weather || null, workforce: Number(form.workforce) || 0,
          work_description: form.work_description, materials: form.materials || null,
          equipment: form.equipment || null, obstacles: form.obstacles || null,
        },
        photos,
        title: `Buku harian ${(form.log_date || "hari ini")} · ${form.work_description.slice(0, 40)}`,
      });
      if (out.queued) {
        toast.success("Buku harian tersimpan di perangkat — terkirim sendiri begitu sinyal "
          + "kembali (termasuk fotonya).");
      } else {
        toast.success(photos.length
          ? `Buku harian tersimpan dengan ${photos.length} foto — tampil juga di kavling terkait.`
          : "Buku harian tersimpan.");
      }
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan catatan."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Tambah Buku Harian</DialogTitle>
          <DialogDescription>Catat aktivitas lapangan hari ini.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="diary-date">Tanggal</Label><Input id="diary-date" data-testid="diary-form-date" type="date" value={form.log_date} onChange={(e) => set("log_date", e.target.value)} /></div>
          <div className="space-y-1.5"><Label>Cuaca</Label>
            <ReferenceSelect group="weather" value={form.weather}
              onChange={(v) => set("weather", v)} testId="diary-form-weather" /></div>
          <div className="space-y-1.5"><Label htmlFor="diary-workforce">Jumlah Pekerja</Label><Input id="diary-workforce" data-testid="diary-form-workforce" type="number" min={0} value={form.workforce} onChange={(e) => set("workforce", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="diary-equipment">Peralatan</Label><Input id="diary-equipment" data-testid="diary-form-equipment" value={form.equipment} onChange={(e) => set("equipment", e.target.value)} placeholder="mis. mixer, vibrator" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="diary-work">Uraian Pekerjaan</Label><Textarea id="diary-work" data-testid="diary-form-work" rows={2} value={form.work_description} onChange={(e) => set("work_description", e.target.value)} placeholder="mis. pengecoran sloof zona A, plester dinding lantai 1" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="diary-materials">Material Diterima/Dipakai</Label><Input id="diary-materials" data-testid="diary-form-materials" value={form.materials} onChange={(e) => set("materials", e.target.value)} placeholder="mis. semen 40 sak, besi 10mm 30 batang" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="diary-obstacles">Kendala</Label><Textarea id="diary-obstacles" data-testid="diary-form-obstacles" rows={2} value={form.obstacles} onChange={(e) => set("obstacles", e.target.value)} placeholder="mis. hujan sejak pukul 13.00, pengiriman keramik tertunda" /></div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Foto dokumentasi (opsional)</Label>
            <PhotoUploader value={photos} onChange={setPhotos} ownerType="site_diary"
              ownerId={projectId} max={4} testId={FIELD.diaryPhotoInput}
              label="Unggah foto buku harian" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FIELD.diaryAddSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
