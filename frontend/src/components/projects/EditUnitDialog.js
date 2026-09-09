import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROJECT_EDIT } from "@/constants/testIds";

/**
 * Ubah master unit: tipe, harga, dan (Fase 28b) luas tanah/bangunan, orientasi, hoek.
 *
 * Sebelum Fase 28b luas hanya DITURUNKAN dari nama tipe ("Tipe 45/90") sehingga kavling
 * dengan luas tidak standar tidak bisa dicatat benar, sedangkan orientasi & hoek sama
 * sekali tidak punya form. Ketiganya dipakai peta, showroom publik, dan harga per m².
 * Harga unit yang sudah booked/terjual dikunci backend agar tagihan & komisi tidak berubah.
 */
export default function EditUnitDialog({ projectId, unit, open, onOpenChange, onDone }) {
  const [form, setForm] = useState({
    type: "", price: "", luas_tanah: "", luas_bangunan: "", orientation: "", corner: false,
  });
  const [busy, setBusy] = useState(false);
  const locked = ["booked", "sold"].includes(unit?.status);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open && unit) {
      setForm({
        type: unit.type || "",
        price: String(unit.price ?? ""),
        luas_tanah: unit.luas_tanah != null ? String(unit.luas_tanah) : "",
        luas_bangunan: unit.luas_bangunan != null ? String(unit.luas_bangunan) : "",
        orientation: unit.orientation || "",
        corner: !!unit.corner,
      });
    }
  }, [open, unit]);

  const num = (v) => (String(v).trim() === "" ? undefined : Math.max(0, Math.round(Number(v) || 0)));

  const submit = async () => {
    setBusy(true);
    try {
      const body = { type: form.type, corner: form.corner };
      if (!locked) body.price = Math.round(Number(form.price) || 0);
      const lt = num(form.luas_tanah);
      const lb = num(form.luas_bangunan);
      if (lt !== undefined) body.luas_tanah = lt;
      if (lb !== undefined) body.luas_bangunan = lb;
      if (form.orientation) body.orientation = form.orientation;
      await api.put(`/projects/${projectId}/units/${unit.id}`, body);
      toast.success(`Unit ${unit.code} diperbarui.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui unit."); }
    finally { setBusy(false); }
  };

  const pricePerM2 = Number(form.price) && Number(form.luas_tanah)
    ? Math.round(Number(form.price) / Number(form.luas_tanah)) : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ubah Unit {unit?.code}</DialogTitle>
          <DialogDescription>
            {locked
              ? `Unit sudah ${unit?.status} — harga dikunci agar tagihan & komisi tetap konsisten.`
              : "Perbaiki spesifikasi kavling: tipe, harga, luas, orientasi, dan hoek."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Tipe Unit</Label>
            <ReferenceSelect group="unit_type" value={form.type} onChange={(v) => set("type", v)}
              testId={PROJECT_EDIT.unitFormType} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="editunitdialog-harga-rp">Harga (Rp)</Label>
            <RupiahInput id="editunitdialog-harga-rp" data-testid={PROJECT_EDIT.unitFormPrice} value={form.price}
              disabled={locked} onChange={(e) => set("price", e.target.value)} />
            <p className="text-xs text-muted-foreground">{formatIDR(Number(form.price) || 0)}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="editunitdialog-luas-tanah-m2">Luas tanah (m²)</Label>
            <Input id="editunitdialog-luas-tanah-m2" data-testid={PROJECT_EDIT.unitFormLuasTanah} type="number" min={0}
              value={form.luas_tanah} placeholder="mis. 120"
              onChange={(e) => set("luas_tanah", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="editunitdialog-luas-bangunan-m2">Luas bangunan (m²)</Label>
            <Input id="editunitdialog-luas-bangunan-m2" data-testid={PROJECT_EDIT.unitFormLuasBangunan} type="number" min={0}
              value={form.luas_bangunan} placeholder="mis. 70"
              onChange={(e) => set("luas_bangunan", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Orientasi (arah hadap)</Label>
            <ReferenceSelect group="unit_orientation" value={form.orientation}
              onChange={(v) => set("orientation", v)} allowEmpty emptyLabel="Belum ditentukan"
              testId={PROJECT_EDIT.unitFormOrientation} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="unit-corner">Kavling hook (sudut)</Label>
            <div className="flex h-10 items-center gap-2 rounded-md border px-3">
              <Checkbox id="unit-corner" data-testid={PROJECT_EDIT.unitFormCorner}
                aria-label="Kavling hook (sudut)" checked={form.corner}
                onCheckedChange={(v) => set("corner", !!v)} />
              <span className="text-sm text-muted-foreground">
                {form.corner ? "Ya, kavling sudut" : "Bukan kavling sudut"}
              </span>
            </div>
          </div>
          {pricePerM2 ? (
            <p className="text-xs text-muted-foreground sm:col-span-2">
              Harga per m² tanah: <span className="font-semibold">{formatIDR(pricePerM2)}</span>
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROJECT_EDIT.unitSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
