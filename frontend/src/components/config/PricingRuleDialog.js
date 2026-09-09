import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import DatePickerField from "@/components/patterns/DatePickerField";
import MultiCheckList from "@/components/config/MultiCheckList";
import api from "@/services/apiClient";
import { PRICING } from "@/constants/testIds";

export const RULE_META = {
  discount_scheme: {
    slug: "discount-schemes", label: "Skema diskon",
    help: "Dipilih sales dari dropdown saat membuat penawaran/reservasi. Tandai “perlu persetujuan” bila manajer harus memutuskan.",
  },
  promo: {
    slug: "promos", label: "Promo",
    help: "Potongan program penjualan yang berlaku pada periode & proyek/tipe unit tertentu.",
  },
  coupon: {
    slug: "coupons", label: "Kupon",
    help: "Kode berperiode dengan kuota total dan kuota per pembeli; setiap pemakaian dicatat dan dilepas bila transaksi batal.",
  },
};

const EMPTY = {
  code: "", name: "", kind: "percent", value: 0, max_amount: 0, applies_project_ids: [],
  applies_unit_types: [], valid_from: "", valid_until: "", active: true, note: "",
  requires_approval: false, stackable: true, quota_total: 0, quota_per_customer: 1,
  target: "price", target_component: "",
};

const TARGET_HELP = {
  price: "Memangkas harga jual; termin mengikuti harga bersih.",
  dp: "Dikurangkan dari termin uang muka (DP) — persen dihitung dari nilai DP.",
  booking_fee: "Booking fee yang harus dibayar berkurang; total kewajiban ikut turun.",
  cost: "Mengurangi satu komponen biaya all-in (BPHTB, notaris, dll.) — hanya berlaku bila skema all-in transaksi memuat komponennya.",
};

/** Dialog buat/ubah satu aturan harga. `source={}` = baru; berisi `id` = ubah. */
export default function PricingRuleDialog({ kind, source, open, onOpenChange, onSaved }) {
  const meta = RULE_META[kind];
  const [form, setForm] = useState(EMPTY);
  const [projects, setProjects] = useState([]);
  const [unitTypes, setUnitTypes] = useState([]);
  const [components, setComponents] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({ ...EMPTY, ...(source || {}), target: source?.target || "price",
      target_component: source?.target_component || "",
      valid_from: (source?.valid_from || "").slice(0, 10),
      valid_until: (source?.valid_until || "").slice(0, 10) });
    api.get("/projects", { params: { limit: 100 } })
      .then((r) => setProjects(r.data.data || [])).catch(() => setProjects([]));
    api.get("/catalog/unit-types", { params: { active: true } })
      .then((r) => setUnitTypes(r.data.data || [])).catch(() => setUnitTypes([]));
    api.get("/cost-components").then((r) => setComponents(r.data.data || [])).catch(() => setComponents([]));
  }, [open, source]);

  const patch = (p) => setForm((f) => ({ ...f, ...p }));
  const isEdit = !!form.id;

  const submit = async () => {
    setBusy(true);
    try {
      const body = {
        name: form.name, kind: form.kind, value: Number(form.value) || 0,
        max_amount: Number(form.max_amount) || 0,
        applies_project_ids: form.applies_project_ids || [],
        applies_unit_types: form.applies_unit_types || [],
        valid_from: form.valid_from || null, valid_until: form.valid_until || null,
        active: !!form.active, note: form.note || null,
        target: form.target || "price",
        target_component: form.target === "cost" ? (form.target_component || null) : null,
        ...(kind === "discount_scheme" ? { requires_approval: !!form.requires_approval } : {}),
        ...(kind === "promo" ? { stackable: !!form.stackable } : {}),
        ...(kind === "coupon" ? { quota_total: Number(form.quota_total) || 0,
          quota_per_customer: Number(form.quota_per_customer) || 0 } : {}),
      };
      const res = isEdit
        ? await api.put(`/pricing/${meta.slug}/${form.id}`, body)
        : await api.post(`/pricing/${meta.slug}`, { ...body, code: form.code });
      toast.success(res.data.message || `${meta.label} disimpan.`);
      onSaved?.(res.data.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || `Gagal menyimpan ${meta.label.toLowerCase()}.`);
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PRICING.dialog} className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Ubah ${meta.label.toLowerCase()} ${form.code}` : `${meta.label} baru`}</DialogTitle>
          <DialogDescription>{meta.help}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[62vh] space-y-3 overflow-y-auto pr-1">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="pr-code">Kode</Label>
              <Input id="pr-code" data-testid={PRICING.formCode} value={form.code} disabled={isEdit}
                placeholder={kind === "coupon" ? "SIPRO2026" : "DISC-CASH"}
                onChange={(e) => patch({ code: e.target.value.toUpperCase() })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pr-name">Nama</Label>
              <Input id="pr-name" data-testid={PRICING.formName} value={form.name}
                placeholder="Diskon pembayaran tunai" onChange={(e) => patch({ name: e.target.value })} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>Jenis nilai</Label>
              <ReferenceSelect group="discount_kind" value={form.kind} testId={PRICING.formKind}
                onChange={(v) => patch({ kind: v })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pr-value">{form.kind === "percent" ? "Persen potongan (%)" : "Nominal potongan (Rp)"}</Label>
              {form.kind === "percent" ? (
                <Input id="pr-value" type="number" step="0.01" data-testid={PRICING.formValue}
                  aria-label="Nilai potongan"
                  value={form.value} onChange={(e) => patch({ value: e.target.value })} />
              ) : (
                <RupiahInput id="pr-value" data-testid={PRICING.formValue} aria-label="Nilai potongan"
                  value={form.value} onChange={(e) => patch({ value: e.target.value })} />
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pr-max">Batas maksimal (Rp, 0 = tanpa batas)</Label>
              <RupiahInput id="pr-max" data-testid={PRICING.formMax}
                value={form.max_amount} onChange={(e) => patch({ max_amount: e.target.value })} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Sasaran potongan</Label>
              <ReferenceSelect group="discount_target" value={form.target} testId={PRICING.formTarget}
                onChange={(v) => patch({ target: v, target_component: v === "cost" ? form.target_component : "" })} />
              <p className="text-xs text-muted-foreground" data-testid={PRICING.formTargetHelp}>
                {TARGET_HELP[form.target] || ""}
                {kind === "coupon" && form.target !== "price" ? " Kupon ini dipotong dari komponen tersebut saat ditebus di reservasi." : ""}
              </p>
            </div>
            {form.target === "cost" ? (
              <div className="space-y-1.5">
                <Label>Komponen biaya yang dipotong</Label>
                <Select value={form.target_component || ""} onValueChange={(v) => patch({ target_component: v })}>
                  <SelectTrigger data-testid={PRICING.formTargetComponent} aria-label="Komponen biaya">
                    <SelectValue placeholder="Pilih komponen…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="*" data-testid={`${PRICING.formTargetComponent}-opt-all`}>SEMUA — seluruh biaya all-in yang ditagih ke pembeli</SelectItem>
                    {components.map((c) => (
                      <SelectItem key={c.code} value={c.code}>{c.code} — {c.label || c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">
                  "SEMUA" memotong total biaya pembeli (BPHTB, notaris, bank, …) berurutan sampai nominal habis — cocok untuk promo "potongan all-in Rp X".
                </p>
              </div>
            ) : null}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Proyek (boleh lebih dari satu)</Label>
              <MultiCheckList testId={PRICING.formProject} allLabel="Semua proyek"
                emptyText="Belum ada proyek."
                options={projects.map((p) => ({ value: p.id, label: p.name }))}
                value={form.applies_project_ids} onChange={(v) => patch({ applies_project_ids: v })} />
            </div>
            <div className="space-y-1.5">
              <Label>Tipe unit (boleh lebih dari satu)</Label>
              <MultiCheckList testId={PRICING.formUnitType} allLabel="Semua tipe unit"
                emptyText="Belum ada tipe unit."
                options={unitTypes.map((t) => ({ value: t.code, label: `${t.code} · ${t.name}` }))}
                value={form.applies_unit_types} onChange={(v) => patch({ applies_unit_types: v })} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="pr-from">Berlaku mulai</Label>
              <DatePickerField id="pr-from" testId={PRICING.formFrom} value={form.valid_from}
                placeholder="Tanpa batas awal" onChange={(v) => patch({ valid_from: v })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pr-until">Berlaku sampai</Label>
              <DatePickerField id="pr-until" testId={PRICING.formUntil} value={form.valid_until}
                placeholder="Tanpa batas akhir" onChange={(v) => patch({ valid_until: v })} />
            </div>
          </div>
          {kind === "coupon" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="pr-quota">Kuota total (0 = tanpa batas)</Label>
                <Input id="pr-quota" type="number" data-testid={PRICING.formQuota}
                  value={form.quota_total} onChange={(e) => patch({ quota_total: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pr-quota-c">Kuota per pembeli (0 = tanpa batas)</Label>
                <Input id="pr-quota-c" type="number" data-testid={PRICING.formQuotaCustomer}
                  value={form.quota_per_customer}
                  onChange={(e) => patch({ quota_per_customer: e.target.value })} />
              </div>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="pr-note">Catatan</Label>
            <Textarea id="pr-note" rows={2} value={form.note || ""}
              onChange={(e) => patch({ note: e.target.value })} />
          </div>
          <div className="flex flex-wrap items-center gap-6">
            {kind === "discount_scheme" ? (
              <div className="flex items-center gap-2">
                <Switch data-testid={PRICING.formApproval} checked={!!form.requires_approval}
                  aria-label="Perlu persetujuan manajer"
                  onCheckedChange={(v) => patch({ requires_approval: v })} />
                <span className="text-sm">Perlu persetujuan manajer</span>
              </div>
            ) : null}
            {kind === "promo" ? (
              <div className="flex items-center gap-2">
                <Switch data-testid={PRICING.formStackable} checked={!!form.stackable}
                  aria-label="Boleh digabung kupon" onCheckedChange={(v) => patch({ stackable: v })} />
                <span className="text-sm">Boleh digabung kupon</span>
              </div>
            ) : null}
            <div className="flex items-center gap-2">
              <Switch data-testid={PRICING.formActive} checked={!!form.active} aria-label="Aktif"
                onCheckedChange={(v) => patch({ active: v })} />
              <span className="text-sm">Aktif</span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={PRICING.submit} onClick={submit}
            disabled={busy || !form.name || (!isEdit && !form.code)}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
