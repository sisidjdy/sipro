import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ASSETS } from "@/constants/testIds";

// Masa manfaat default per kelompok fiskal (Pasal 11 UU PPh / PMK 72-2023).
// Hanya USULAN untuk mempermudah input; nilainya tetap bisa diubah manual dan
// backend yang menjadi sumber kebenaran.
const LIFE_SUGGESTION = {
  kelompok_1: 48, kelompok_2: 96, kelompok_3: 192, kelompok_4: 240,
  bangunan_permanen: 240, bangunan_tidak_permanen: 120, tidak_disusutkan: 0,
};

/** Form pendaftaran aset tetap (perolehan langsung berjurnal). */
export default function AddAssetDialog({ open, onOpenChange, onSaved }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("kendaraan");
  const [taxGroup, setTaxGroup] = useState("kelompok_2");
  const [method, setMethod] = useState("garis_lurus");
  const [cost, setCost] = useState("");
  const [salvage, setSalvage] = useState("0");
  const [life, setLife] = useState("96");
  const [acquired, setAcquired] = useState("");
  const [funding, setFunding] = useState("bank");
  const [vendor, setVendor] = useState("");
  const [projectId, setProjectId] = useState("");
  const [location, setLocation] = useState("");
  const [note, setNote] = useState("");
  const [projects, setProjects] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const loadProjects = useCallback(async () => {
    try {
      const res = await api.get("/projects?limit=100");
      setProjects(res.data.data || []);
    } catch (e) { setProjects([]); }
  }, []);

  useEffect(() => { if (open) { loadProjects(); setErr(""); } }, [open, loadProjects]);

  const pickTaxGroup = (v) => {
    setTaxGroup(v);
    const suggested = LIFE_SUGGESTION[v];
    if (suggested !== undefined) setLife(String(suggested));
    if (v === "tidak_disusutkan") setMethod("tidak_disusutkan");
    else if (method === "tidak_disusutkan") setMethod("garis_lurus");
  };

  const monthly = (() => {
    const c = Number(cost) || 0; const s = Number(salvage) || 0; const l = Number(life) || 0;
    if (method === "tidak_disusutkan" || l <= 0 || c <= s) return 0;
    if (method === "saldo_menurun") return Math.round(c * (2 / l));
    return Math.round((c - s) / l);
  })();

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post("/fixed-assets/assets", {
        name, category, tax_group: taxGroup, method, cost: Number(cost),
        salvage_value: Number(salvage) || 0,
        useful_life_months: Number(life) || 0,
        acquired_date: acquired ? new Date(acquired).toISOString() : null,
        funding, vendor: vendor || null, project_id: projectId || null,
        location: location || null, note: note || null,
      });
      toast.success("Aset tetap tercatat beserta jurnal perolehannya.");
      onOpenChange(false);
      setName(""); setCost(""); setSalvage("0"); setVendor(""); setLocation(""); setNote("");
      onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal menyimpan aset tetap.");
    } finally { setSaving(false); }
  };

  const valid = name.trim().length >= 3 && Number(cost) > 0
    && Number(salvage) < Number(cost)
    && (method === "tidak_disusutkan" || Number(life) > 0)
    && (funding !== "utang_usaha" || vendor.trim().length > 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={ASSETS.addDialog} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Tambah Aset Tetap</DialogTitle>
          <DialogDescription>
            Perolehan langsung dibukukan: Dr 1-2100 Aset Tetap / Cr kas, bank, atau utang usaha.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="as-name">Nama aset</Label>
            <Input id="as-name" data-testid={ASSETS.addName} value={name}
              placeholder="Mis. Toyota Avanza operasional pemasaran"
              onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Kategori aset</Label>
            <ReferenceSelect group="asset_category" value={category} onChange={setCategory}
              testId={ASSETS.addCategory} />
          </div>
          <div className="space-y-1.5">
            <Label>Kelompok fiskal</Label>
            <ReferenceSelect group="asset_tax_group" value={taxGroup} onChange={pickTaxGroup}
              testId={ASSETS.addTaxGroup} />
          </div>
          <div className="space-y-1.5">
            <Label>Metode penyusutan</Label>
            <ReferenceSelect group="depreciation_method" value={method} onChange={setMethod}
              testId={ASSETS.addMethod} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-life">Umur manfaat (bulan)</Label>
            <Input id="as-life" data-testid={ASSETS.addLife} type="number" min="0" value={life}
              onChange={(e) => setLife(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-cost">Harga perolehan (Rp)</Label>
            <RupiahInput id="as-cost" data-testid={ASSETS.addCost} value={cost}
              onChange={(e) => setCost(e.target.value)} placeholder="0" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-salvage">Nilai residu (Rp)</Label>
            <RupiahInput id="as-salvage" data-testid={ASSETS.addSalvage}
              value={salvage} onChange={(e) => setSalvage(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-acquired">Tanggal perolehan</Label>
            <Input id="as-acquired" data-testid={ASSETS.addAcquired} type="date" value={acquired}
              onChange={(e) => setAcquired(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Sumber dana</Label>
            <ReferenceSelect group="asset_funding" value={funding} onChange={setFunding}
              testId={ASSETS.addFunding} />
          </div>
          <div className="space-y-1.5">
            <Label>Vendor {funding === "utang_usaha" ? "(wajib)" : "(opsional)"}</Label>
            <ReferenceSelect group="vendor" value={vendor} onChange={setVendor}
              testId={ASSETS.addVendor} placeholder="Pilih vendor…" />
          </div>
          <div className="space-y-1.5">
            <Label>Proyek (opsional)</Label>
            <Select value={projectId || "__none__"}
              onValueChange={(v) => setProjectId(v === "__none__" ? "" : v)}>
              <SelectTrigger data-testid={ASSETS.addProject}>
                <SelectValue placeholder="Tanpa proyek" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Tanpa proyek</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-loc">Lokasi / penempatan</Label>
            <Input id="as-loc" data-testid={ASSETS.addLocation} value={location}
              placeholder="Mis. Kantor pemasaran"
              onChange={(e) => setLocation(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="as-note">Catatan</Label>
            <Textarea id="as-note" value={note} rows={2}
              onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>

        <div className="rounded-lg border bg-secondary/40 p-3 text-sm">
          Estimasi beban penyusutan per bulan:{" "}
          <span className="font-semibold tabular-nums">{formatIDR(monthly)}</span>
          {funding === "utang_usaha" ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Pembelian secara utang otomatis membuat tagihan vendor di menu Utang (AP)
              sehingga bisa dibayar dan tetap tie-out dengan buku besar.
            </p>
          ) : null}
        </div>
        {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={ASSETS.addSubmit} disabled={!valid || saving} onClick={submit}>
            {saving ? "Menyimpan…" : "Simpan Aset"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
