import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import PhotoUploader from "@/components/patterns/PhotoUploader";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import * as sync from "@/services/offlineSync";
import { FIELD } from "@/constants/testIds";

const EMPTY = { title: "", description: "", location: "", category: "finishing", severity: "medium", due_date: "", unit_id: "" };

export default function AddPunchDialog({ projectId, open, onOpenChange, onDone, units = [],
  unitId = null }) {
  const [form, setForm] = useState(EMPTY);
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  // Fase 46: dialog ini juga dipakai dari Unit 360 → unit sudah pasti, jadi langsung
  // terisi (dulu pemakai harus memilih ulang unit yang sedang ia buka).
  useEffect(() => {
    if (open) { setForm({ ...EMPTY, unit_id: unitId || "" }); setPhotos([]); }
  }, [open, unitId]);

  const submit = async () => {
    if (!form.title.trim()) { toast.error("Isi judul temuan."); return; }
    setBusy(true);
    try {
      // Fase 50B: temuan biasanya dicatat saat berjalan di lokasi. Tanpa sinyal, temuan +
      // fotonya MASUK ANTREAN perangkat; `client_ref` menjaga agar kiriman ulang tidak
      // melahirkan temuan kembar (dan tugas perbaikan kembar).
      const out = await sync.submitOrQueue({
        kind: "punch_create",
        payload: {
          project_id: projectId, title: form.title, description: form.description || null,
          location: form.location || null, category: form.category, severity: form.severity,
          unit_id: form.unit_id || null,
          due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
        },
        photos,
        title: form.title.slice(0, 50),
      });
      toast.success(out.queued
        ? "Temuan tersimpan di perangkat — terkirim sendiri begitu sinyal kembali."
        : "Item punch ditambahkan — tugas perbaikan dibuat.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah item."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Tambah Item Punch List</DialogTitle>
          <DialogDescription>Catat cacat/temuan yang perlu diperbaiki.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="addpunchdialog-judul-temuan">Judul Temuan</Label><Input id="addpunchdialog-judul-temuan" value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="mis. Retak rambut plafon" /></div>
          <div className="space-y-1.5"><Label>Kavling terkait</Label>
            <Select value={form.unit_id || "__none__"}
              onValueChange={(v) => set("unit_id", v === "__none__" ? "" : v)}>
              <SelectTrigger data-testid="punch-form-unit" aria-label="Kavling terkait">
                <SelectValue placeholder="Tanpa kavling" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Tanpa kavling (umum proyek)</SelectItem>
                {units.map((u) => (
                  <SelectItem key={u.id} value={u.id}>{u.code}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5"><Label htmlFor="addpunchdialog-lokasi">Lokasi</Label><Input id="addpunchdialog-lokasi" value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="mis. Ruang Tamu" /></div>
          <div className="space-y-1.5"><Label>Kategori</Label>
            <ReferenceSelect group="work_category" value={form.category}
              onChange={(v) => set("category", v)} testId="punch-form-category" /></div>
          <div className="space-y-1.5"><Label>Prioritas</Label>
            <ReferenceSelect group="punch_severity" value={form.severity}
              onChange={(v) => set("severity", v)} testId="punch-form-severity" /></div>
          <div className="space-y-1.5"><Label htmlFor="addpunchdialog-tenggat">Tenggat</Label><Input id="addpunchdialog-tenggat" type="date" value={form.due_date} onChange={(e) => set("due_date", e.target.value)} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="addpunchdialog-deskripsi">Deskripsi</Label><Textarea id="addpunchdialog-deskripsi" rows={2} value={form.description} onChange={(e) => set("description", e.target.value)} /></div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Foto temuan (opsional)</Label>
            <PhotoUploader value={photos} onChange={setPhotos} ownerType="punch_item"
              ownerId={projectId} max={4} testId={FIELD.punchPhotoInput}
              label="Unggah foto temuan" />
            <p className="text-[11px] text-muted-foreground">
              Foto pada kavling terkait otomatis tampil di galeri kavling (Site Plan) dan portal pembeli.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FIELD.punchAddSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
