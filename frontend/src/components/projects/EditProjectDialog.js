import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { PROJECT_EDIT } from "@/constants/testIds";

/**
 * Ubah master proyek. Endpoint PUT /projects/{id} baru ditambahkan setelah audit
 * (sebelumnya nama/kode/lokasi/status proyek tidak bisa dikoreksi setelah dibuat).
 * Perubahan nama otomatis disamakan ke seluruh dokumen anak (RAB, SPK, PO, izin, dll).
 */
export default function EditProjectDialog({ project, open, onOpenChange, onDone }) {
  const [form, setForm] = useState({ name: "", code: "", location: "", marketing_office: "", status: "active" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open && project) {
      setForm({
        name: project.name || "", code: project.code || "",
        location: project.location || "", marketing_office: project.marketing_office || "",
        status: project.status || "active",
      });
    }
  }, [open, project]);

  const submit = async () => {
    if (!form.name.trim() || !form.code.trim()) { toast.error("Nama & kode proyek wajib diisi."); return; }
    setBusy(true);
    try {
      const res = await api.put(`/projects/${project.id}`, form);
      const synced = res.data?.denorm_synced || 0;
      toast.success(synced
        ? `Proyek diperbarui. ${synced} dokumen terkait ikut disamakan.`
        : "Proyek diperbarui.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui proyek."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Ubah Proyek</DialogTitle>
          <DialogDescription>
            Nama baru otomatis disinkronkan ke RAB, SPK, PO, perizinan, dan dokumen lain
            agar tidak ada nama lama yang tertinggal.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="editprojectdialog-nama-proyek">Nama Proyek</Label>
            <Input id="editprojectdialog-nama-proyek" data-testid={PROJECT_EDIT.formName} value={form.name}
              onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="editprojectdialog-kode">Kode</Label>
            <Input id="editprojectdialog-kode" data-testid={PROJECT_EDIT.formCode} value={form.code}
              onChange={(e) => set("code", e.target.value.toUpperCase())} />
          </div>
          <div className="space-y-1.5">
            <Label>Status</Label>
            <ReferenceSelect group="project_status" value={form.status}
              onChange={(v) => set("status", v)} testId={PROJECT_EDIT.formStatus} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="editprojectdialog-lokasi">Lokasi</Label>
            <Input id="editprojectdialog-lokasi" data-testid={PROJECT_EDIT.formLocation} value={form.location}
              onChange={(e) => set("location", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="editprojectdialog-kantor">Alamat kantor pemasaran</Label>
            <Input id="editprojectdialog-kantor" data-testid={PROJECT_EDIT.formMarketingOffice} value={form.marketing_office}
              placeholder="mis. Marketing Gallery Jl. Raya Serpong No. 12, Tangerang"
              onChange={(e) => set("marketing_office", e.target.value)} />
            <p className="text-[11px] text-muted-foreground">Dipakai sebagai lokasi bawaan saat menjadwalkan survei lead.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROJECT_EDIT.submit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
