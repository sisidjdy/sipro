import React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import api from "@/services/apiClient";
import { CONFIG } from "@/constants/testIds";

export const EMPTY_UNIT_TYPE = {
  code: "", name: "", building_area: 30, land_area_std: 60, base_price: 0, bedrooms: 2,
  bathrooms: 1, floors: 1, active: true,
};

/** Satu form master TIPE UNIT — dipakai Pusat Konfigurasi & dialog "Buat unit" di Master Proyek. */
export function UnitTypeFormDialog({ form, setForm, onSaved }) {
  const submit = async () => {
    try {
      const body = {
        ...form,
        building_area: Number(form.building_area) || 0,
        land_area_std: Number(form.land_area_std) || 0,
        base_price: Number(form.base_price) || 0,
      };
      let saved;
      if (form.id) {
        const { id, code, org_id, created_at, updated_at, units_count, ...patch } = body;
        saved = (await api.put(`/catalog/unit-types/${form.id}`, { ...patch, needs_review: false })).data.data;
      } else {
        saved = (await api.post("/catalog/unit-types", body)).data.data;
      }
      toast.success("Tipe unit disimpan.");
      setForm(null); onSaved(saved || body);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan tipe unit.");
    }
  };

  return (
    <Dialog open={!!form} onOpenChange={(o) => { if (!o) setForm(null); }}>
      <DialogContent data-testid="unit-type-form-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{form?.id ? "Ubah tipe unit" : "Tipe unit baru"}</DialogTitle>
          <DialogDescription>
            Harga dasar dipakai saat membuat unit (dikalikan pengali harga cluster). Tipe ini
            langsung tersedia di Pusat Konfigurasi › Tipe Unit dan di dialog Buat unit.
          </DialogDescription>
        </DialogHeader>
        {form ? (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="ut-code">Kode</Label>
                <Input id="ut-code" data-testid={CONFIG.typeFormCode} value={form.code}
                  disabled={!!form.id} placeholder="otomatis dari aturan penomoran bila kosong"
                  onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ut-name">Nama tipe</Label>
                <Input id="ut-name" data-testid={CONFIG.typeFormName} value={form.name}
                  placeholder="Tipe 30/60"
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="ut-lb">Luas bangunan (m²)</Label>
                <Input id="ut-lb" data-testid={CONFIG.typeFormBuilding} type="number"
                  value={form.building_area ?? ""}
                  onChange={(e) => setForm({ ...form, building_area: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ut-lt">Luas tanah standar (m²)</Label>
                <Input id="ut-lt" data-testid={CONFIG.typeFormLand} type="number"
                  value={form.land_area_std ?? ""}
                  onChange={(e) => setForm({ ...form, land_area_std: e.target.value })} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ut-price">Harga dasar (Rp)</Label>
              <RupiahInput id="ut-price" data-testid={CONFIG.typeFormPrice}
                value={form.base_price ?? ""}
                onChange={(e) => setForm({ ...form, base_price: e.target.value })} />
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="ut-kt">Kamar tidur</Label>
                <Input id="ut-kt" type="number" value={form.bedrooms ?? ""}
                  onChange={(e) => setForm({ ...form, bedrooms: Number(e.target.value) })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ut-km">Kamar mandi</Label>
                <Input id="ut-km" type="number" value={form.bathrooms ?? ""}
                  onChange={(e) => setForm({ ...form, bathrooms: Number(e.target.value) })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ut-fl">Jumlah lantai</Label>
                <Input id="ut-fl" type="number" value={form.floors ?? 1}
                  onChange={(e) => setForm({ ...form, floors: Number(e.target.value) })} />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={!!form.active} aria-label="Aktif"
                onCheckedChange={(v) => setForm({ ...form, active: v })} />
              <span className="text-sm">Aktif (bisa dipakai membuat unit)</span>
            </div>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => setForm(null)}>Batal</Button>
          <Button data-testid={CONFIG.typeSubmit} onClick={submit} disabled={!form?.name}>Simpan</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
