import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { PARTNERS } from "@/constants/testIds";

const EMPTY = {
  name: "", partner_id: "", basis: "percent_price", value: 2, price_base: "gross",
  period: "monthly", qualify_rule: "survey_attended", trigger: "ppjb_signed",
  tax_type: "", tax_rate: "", gross_up: false, project_id: "", unit_type: "",
  valid_from: "", valid_to: "", status: "active", note: "",
};
const NEEDS_VALUE = ["percent_price", "fixed_per_deal", "per_lead_qualified"];
const NEEDS_TIERS = ["tier_volume", "tier_value"];

/**
 * FeeRuleFormDialog — satu formulir untuk SEMUA dasar fee (keputusan pemilik D5).
 *
 * Field yang tampil mengikuti dasar fee yang dipilih; validasi berat (total porsi 100%,
 * tier tidak bolong/tumpang tindih) tetap DI SERVER supaya aturan yang tidak bisa dieksekusi
 * tidak pernah tersimpan — pesan galatnya ditampilkan apa adanya di sini.
 */
export default function FeeRuleFormDialog({ rule, open, onOpenChange, onDone }) {
  const editing = Boolean(rule?.id);
  const { options } = useReference();
  const [form, setForm] = useState(EMPTY);
  const [splits, setSplits] = useState([]);
  const [tiers, setTiers] = useState([]);
  const [unitTypes, setUnitTypes] = useState([]);
  const [partners, setPartners] = useState([]);
  const [projects, setProjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!open) return;
    api.get("/partners", { params: { limit: 200 } })
      .then((r) => setPartners(r.data.data || [])).catch(() => setPartners([]));
    api.get("/projects").then((r) => setProjects(r.data.data || [])).catch(() => setProjects([]));
    setForm({
      ...EMPTY,
      ...Object.fromEntries(Object.keys(EMPTY)
        .filter((k) => rule?.[k] !== undefined && rule?.[k] !== null)
        .map((k) => [k, rule[k]])),
      partner_id: rule?.partner_id || "",
      tax_type: rule?.tax?.pph_type || "",
      tax_rate: rule?.tax?.rate ?? "",
      gross_up: Boolean(rule?.tax?.gross_up),
      project_id: rule?.scope?.project_id || "",
      unit_type: rule?.scope?.unit_type || "",
      valid_from: (rule?.valid_from || "").slice(0, 10),
      valid_to: (rule?.valid_to || "").slice(0, 10),
    });
    setSplits(rule?.splits?.length ? rule.splits : []);
    setTiers(rule?.tiers?.length ? rule.tiers
      : [{ min: 0, max: 2, value: 1.5, mode: "percent" },
         { min: 3, max: null, value: 2.5, mode: "percent" }]);
    setUnitTypes(Object.entries(rule?.by_unit_type || {}).map(([code, amount]) => ({
      code, amount,
    })));
  }, [open, rule]);

  const showValue = NEEDS_VALUE.includes(form.basis);
  const showTiers = NEEDS_TIERS.includes(form.basis);
  // Satu sumber untuk teks field nominal: dipakai <Label> DAN aria-label input, supaya
  // pembaca layar mendengar arti yang sama dengan yang dilihat mata (persen vs rupiah).
  const valueLabel = form.basis === "percent_price" ? "Persentase (%)" : "Nominal (Rp)";
  const showUnitTable = form.basis === "fixed_per_unit_type";
  const splitTotal = useMemo(() => splits.reduce((n, s) => n + Number(s.pct || 0), 0), [splits]);

  const submit = async () => {
    const body = {
      name: form.name.trim(), basis: form.basis, status: form.status,
      partner_id: form.partner_id || null, price_base: form.price_base,
      note: form.note || null,
      valid_from: form.valid_from || null, valid_to: form.valid_to || null,
      scope: {
        ...(form.project_id ? { project_id: form.project_id } : {}),
        ...(form.unit_type ? { unit_type: form.unit_type } : {}),
      },
      tax: {
        ...(form.tax_type ? { pph_type: form.tax_type } : {}),
        ...(form.tax_rate !== "" ? { rate: Number(form.tax_rate) } : {}),
        gross_up: Boolean(form.gross_up),
      },
    };
    if (showValue) body.value = Number(form.value);
    if (showTiers) {
      body.period = form.period;
      body.tiers = tiers.map((t) => ({
        min: Number(t.min || 0), max: t.max === null || t.max === "" ? null : Number(t.max),
        value: Number(t.value), mode: t.mode || "percent",
      }));
    }
    if (showUnitTable) {
      body.by_unit_type = Object.fromEntries(unitTypes
        .filter((u) => u.code && Number(u.amount) > 0)
        .map((u) => [u.code, Number(u.amount)]));
    }
    if (form.basis === "per_lead_qualified") body.qualify_rule = form.qualify_rule;
    if (splits.length) {
      body.splits = splits.map((s) => ({ trigger: s.trigger, pct: Number(s.pct) }));
    } else {
      body.trigger = form.trigger;
    }
    if (!body.name || body.name.length < 4) {
      toast.error("Nama aturan minimal 4 karakter (dipakai di tagihan fee)."); return;
    }
    setBusy(true);
    try {
      if (editing) await api.put(`/partners/rules/${rule.id}`, body);
      else await api.post("/partners/rules", body);
      toast.success(editing ? "Aturan fee diperbarui." : "Aturan fee dibuat.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan aturan fee.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PARTNERS.ruleForm}
        className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{editing ? `Ubah Aturan — ${rule.code}` : "Aturan Fee Mitra"}</DialogTitle>
          <DialogDescription>
            Aturan paling SPESIFIK yang menang (mitra &gt; tipe unit &gt; cluster &gt; proyek).
            Kalau dua aturan sama spesifik, sistem menolak menerbitkan fee dan menyebut
            kodenya — bukan memilih diam-diam.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="rname">Nama aturan</Label>
            <Input id="rname" data-testid={PARTNERS.ruleName} value={form.name}
              placeholder="Mis. Broker — 2% harga jual, bayar 50% PPJB & 50% AJB"
              onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Berlaku untuk mitra</Label>
            <Select value={form.partner_id || "__all__"}
              onValueChange={(v) => set("partner_id", v === "__all__" ? "" : v)}>
              <SelectTrigger data-testid={PARTNERS.rulePartner} aria-label="Mitra">
                <SelectValue placeholder="Semua mitra" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua mitra (aturan umum)</SelectItem>
                {partners.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Dasar fee</Label>
            <ReferenceSelect group="partner_fee_basis" value={form.basis}
              onChange={(v) => set("basis", v)} testId={PARTNERS.ruleBasis} />
          </div>

          {showValue ? (
            <div className="space-y-1.5">
              <Label htmlFor="rvalue">{valueLabel}</Label>
              {form.basis === "percent_price" ? (
                <Input id="rvalue" type="number" step="0.01" data-testid={PARTNERS.ruleValue}
                  aria-label={valueLabel}
                  value={form.value} onChange={(e) => set("value", e.target.value)} />
              ) : (
                <RupiahInput id="rvalue" data-testid={PARTNERS.ruleValue} aria-label={valueLabel}
                  value={form.value} onChange={(e) => set("value", e.target.value)} />
              )}
            </div>
          ) : null}
          {form.basis === "percent_price" || showTiers ? (
            <div className="space-y-1.5">
              <Label>Dasar harga</Label>
              <ReferenceSelect group="partner_price_base" value={form.price_base}
                onChange={(v) => set("price_base", v)} testId={PARTNERS.rulePriceBase} />
            </div>
          ) : null}
          {form.basis === "per_lead_qualified" ? (
            <div className="space-y-1.5">
              <Label>Syarat lead terkualifikasi</Label>
              <ReferenceSelect group="partner_qualify_rule" value={form.qualify_rule}
                onChange={(v) => set("qualify_rule", v)} testId={PARTNERS.ruleQualify} />
            </div>
          ) : null}

          {showTiers ? (
            <div className="space-y-2 rounded-md border bg-secondary/40 p-3 sm:col-span-2">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Tingkat (tier)</p>
                  <p className="text-xs text-muted-foreground">
                    Harus mulai dari 0, berurutan, tanpa celah &amp; tanpa tumpang tindih.
                    Kosongkan batas atas tingkat terakhir = tanpa batas.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <ReferenceSelect group="partner_fee_period" value={form.period}
                    onChange={(v) => set("period", v)} testId={PARTNERS.rulePeriod}
                    className="w-40" />
                  <Button type="button" size="sm" variant="outline"
                    data-testid={PARTNERS.ruleTierAdd}
                    onClick={() => setTiers((t) => [...t, { min: "", max: null, value: "",
                      mode: "percent" }])}>
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              {tiers.map((t, i) => (
                <div key={`tier-${i}`} className="grid grid-cols-9 items-center gap-2">
                  <Input className="col-span-2" type="number" placeholder="dari"
                    data-testid={PARTNERS.ruleTierMin} data-index={i}
                    aria-label={`Batas bawah tingkat ${i + 1}`} value={t.min ?? ""}
                    onChange={(e) => setTiers((arr) => arr.map((x, j) => j === i
                      ? { ...x, min: e.target.value } : x))} />
                  <Input className="col-span-2" type="number" placeholder="s/d (kosong = ∞)"
                    data-testid={PARTNERS.ruleTierMax} data-index={i}
                    aria-label={`Batas atas tingkat ${i + 1}`} value={t.max ?? ""}
                    onChange={(e) => setTiers((arr) => arr.map((x, j) => j === i
                      ? { ...x, max: e.target.value === "" ? null : e.target.value } : x))} />
                  <Input className="col-span-2" type="number" step="0.01" placeholder="nilai"
                    data-testid={PARTNERS.ruleTierValue} data-index={i}
                    aria-label={`Nilai tingkat ${i + 1}`} value={t.value ?? ""}
                    onChange={(e) => setTiers((arr) => arr.map((x, j) => j === i
                      ? { ...x, value: e.target.value } : x))} />
                  <Select value={t.mode || "percent"}
                    onValueChange={(v) => setTiers((arr) => arr.map((x, j) => j === i
                      ? { ...x, mode: v } : x))}>
                    <SelectTrigger className="col-span-2" data-testid={PARTNERS.ruleTierMode}
                      data-index={i} aria-label={`Mode tingkat ${i + 1}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {options("partner_tier_mode").map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button type="button" size="sm" variant="ghost"
                    aria-label={`Hapus tingkat ${i + 1}`}
                    onClick={() => setTiers((arr) => arr.filter((_, j) => j !== i))}>
                    <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                  </Button>
                </div>
              ))}
            </div>
          ) : null}

          {showUnitTable ? (
            <div className="space-y-2 rounded-md border bg-secondary/40 p-3 sm:col-span-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Nominal per tipe unit</p>
                <Button type="button" size="sm" variant="outline"
                  data-testid={PARTNERS.ruleUnitTypeAdd}
                  onClick={() => setUnitTypes((u) => [...u, { code: "", amount: "" }])}>
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </div>
              {unitTypes.map((u, i) => (
                <div key={`ut-${i}`} className="grid grid-cols-7 items-center gap-2">
                  <Input className="col-span-3" placeholder="Kode tipe unit (mis. TIPE-45-90)"
                    data-testid={PARTNERS.ruleUnitTypeCode} data-index={i}
                    aria-label={`Kode tipe unit ${i + 1}`} value={u.code}
                    onChange={(e) => setUnitTypes((arr) => arr.map((x, j) => j === i
                      ? { ...x, code: e.target.value.toUpperCase() } : x))} />
                  <RupiahInput className="col-span-3" placeholder="Nominal fee (Rp)"
                    data-testid={PARTNERS.ruleUnitTypeAmount} data-index={i}
                    aria-label={`Nominal tipe unit ${i + 1}`} value={u.amount}
                    onChange={(e) => setUnitTypes((arr) => arr.map((x, j) => j === i
                      ? { ...x, amount: e.target.value } : x))} />
                  <Button type="button" size="sm" variant="ghost"
                    aria-label={`Hapus tipe unit ${i + 1}`}
                    onClick={() => setUnitTypes((arr) => arr.filter((_, j) => j !== i))}>
                    <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                  </Button>
                </div>
              ))}
            </div>
          ) : null}

          <div className="space-y-2 rounded-md border bg-secondary/40 p-3 sm:col-span-2">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Pemicu hak fee</p>
                <p className="text-xs text-muted-foreground">
                  Satu pemicu = fee penuh saat itu. Beberapa pemicu = pembayaran bertahap
                  (total wajib 100%, sekarang <strong>{splitTotal}%</strong>).
                </p>
              </div>
              <Button type="button" size="sm" variant="outline"
                data-testid={PARTNERS.ruleSplitAdd}
                onClick={() => setSplits((s) => [...s,
                  { trigger: s.length ? "ajb_signed" : "ppjb_signed", pct: s.length ? 50 : 50 }])}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Tahap
              </Button>
            </div>
            {splits.length === 0 ? (
              <div className="space-y-1.5">
                <Label>Pemicu tunggal</Label>
                <ReferenceSelect group="partner_fee_trigger" value={form.trigger}
                  onChange={(v) => set("trigger", v)} testId={PARTNERS.ruleTrigger} />
              </div>
            ) : splits.map((s, i) => (
              <div key={`split-${i}`} className="grid grid-cols-8 items-center gap-2">
                <div className="col-span-5">
                  <ReferenceSelect group="partner_fee_trigger" value={s.trigger}
                    onChange={(v) => setSplits((arr) => arr.map((x, j) => j === i
                      ? { ...x, trigger: v } : x))}
                    testId={`${PARTNERS.ruleSplitTrigger}-${i}`} />
                </div>
                <Input className="col-span-2" type="number" placeholder="%"
                  data-testid={PARTNERS.ruleSplitPct} data-index={i}
                  aria-label={`Porsi tahap ${i + 1}`} value={s.pct}
                  onChange={(e) => setSplits((arr) => arr.map((x, j) => j === i
                    ? { ...x, pct: e.target.value } : x))} />
                <Button type="button" size="sm" variant="ghost"
                  aria-label={`Hapus tahap ${i + 1}`}
                  onClick={() => setSplits((arr) => arr.filter((_, j) => j !== i))}>
                  <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                </Button>
              </div>
            ))}
          </div>

          <div className="space-y-1.5">
            <Label>Jenis PPh</Label>
            <Select value={form.tax_type || "__auto__"}
              onValueChange={(v) => set("tax_type", v === "__auto__" ? "" : v)}>
              <SelectTrigger data-testid={PARTNERS.ruleTaxType} aria-label="Jenis PPh">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__auto__">Ikut bentuk badan mitra</SelectItem>
                {options("partner_tax_type").map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rtax">Tarif PPh (%) — kosong = tarif Pusat Konfigurasi</Label>
            <Input id="rtax" type="number" step="0.1" data-testid={PARTNERS.ruleTaxRate}
              value={form.tax_rate} onChange={(e) => set("tax_rate", e.target.value)} />
          </div>
          <div className="flex items-center gap-2 sm:col-span-2">
            <Switch data-testid={PARTNERS.ruleGrossUp} checked={form.gross_up}
              onCheckedChange={(v) => set("gross_up", v)} id="rgu" />
            <Label htmlFor="rgu" className="text-sm">
              Gross-up (mitra menerima utuh, PPh ditanggung perusahaan)
            </Label>
          </div>

          <div className="space-y-1.5">
            <Label>Batasi ke proyek (opsional)</Label>
            <Select value={form.project_id || "__all__"}
              onValueChange={(v) => set("project_id", v === "__all__" ? "" : v)}>
              <SelectTrigger data-testid={PARTNERS.ruleProject} aria-label="Proyek">
                <SelectValue placeholder="Semua proyek" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua proyek</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rut">Batasi ke tipe unit (opsional)</Label>
            <ReferenceSelect group="unit_type" value={form.unit_type} allowEmpty
              emptyLabel="Semua tipe unit" onChange={(v) => set("unit_type", v)}
              testId={PARTNERS.ruleUnitTypeScope} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rvf">Berlaku dari</Label>
            <Input id="rvf" type="date" data-testid={PARTNERS.ruleValidFrom}
              value={form.valid_from} onChange={(e) => set("valid_from", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rvt">Berlaku sampai</Label>
            <Input id="rvt" type="date" data-testid={PARTNERS.ruleValidTo}
              value={form.valid_to} onChange={(e) => set("valid_to", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Status</Label>
            <ReferenceSelect group="partner_rule_status" value={form.status}
              onChange={(v) => set("status", v)} testId={PARTNERS.ruleStatus} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="rnote">Catatan</Label>
            <Textarea id="rnote" rows={2} value={form.note}
              onChange={(e) => set("note", e.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={PARTNERS.ruleSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : (editing ? "Simpan Perubahan" : "Simpan Aturan")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
