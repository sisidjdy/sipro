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

/** Ubah nama/satuan material (PUT /materials/{id}) — master material dulu tak bisa dikoreksi. */
export default function EditMaterialDialog({ material, open, onOpenChange, onDone }) {
  const [name, setName] = useState("");
  const [uom, setUom] = useState("unit");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open && material) { setName(material.name || ""); setUom(material.uom || "unit"); }
  }, [open, material]);

  const submit = async () => {
    if (!name.trim()) { toast.error("Nama material wajib diisi."); return; }
    setBusy(true);
    try {
      await api.put(`/materials/${material.id}`, { name, uom });
      toast.success("Material diperbarui.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui material."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ubah Material {material?.code}</DialogTitle>
          <DialogDescription>Perbaiki nama atau satuan agar stok & RAB konsisten.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="material-edit-name-input">Nama</Label>
            <Input id="material-edit-name-input" data-testid="material-edit-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Satuan</Label>
            <ReferenceSelect group="uom" value={uom} onChange={setUom} testId="material-edit-uom" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid="material-edit-submit" onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
