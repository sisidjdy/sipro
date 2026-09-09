import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Plus, TicketPercent, Trash2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import AllinSchemeField from "@/components/pricing/AllinSchemeField";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";

const NONE = "__none__";

/**
 * PricingFields — field harga BERSAMA untuk dialog penawaran dan dialog reservasi.
 *
 * Potongan tidak pernah diketik: skema diskon & promo dipilih dari aturan yang berlaku untuk
 * unit ini (`GET /pricing/options`), kupon diverifikasi server (`/pricing/coupons/validate`).
 * Angka akhir selalu hasil `POST /quotations/simulate` — satu mesin harga.
 */
export default function PricingFields({
  form, set, setKpr, unitId, leadId, schemes = [], addonMaster = [], ids, showKpr = true, showCosts = false, price = 0,
}) {
  const [rules, setRules] = useState({ discount_schemes: [], promos: [] });
  const [addonPick, setAddonPick] = useState("");
  const [coupon, setCoupon] = useState(null);

  useEffect(() => {
    setCoupon(null);
    if (!unitId) { setRules({ discount_schemes: [], promos: [] }); return; }
    api.get("/pricing/options", { params: { unit_id: unitId, lead_id: leadId || undefined } })
      .then((r) => setRules(r.data.data || { discount_schemes: [], promos: [] }))
      .catch(() => setRules({ discount_schemes: [], promos: [] }));
  }, [unitId, leadId]);

  const addAddon = () => {
    const master = addonMaster.find((a) => a.code === addonPick);
    if (!master) return;
    if (form.addons.some((a) => a.code === master.code)) {
      toast.info("Tambahan itu sudah ada di daftar."); return;
    }
    set({ addons: [...form.addons, { code: master.code, qty: 1, name: master.name }] });
    setAddonPick("");
  };

  const checkCoupon = async () => {
    const code = (form.coupon_code || "").trim();
    if (!code) { setCoupon(null); return; }
    if (!unitId) { setCoupon({ ok: false, text: "Pilih unit lebih dulu." }); return; }
    try {
      const res = await api.post("/pricing/coupons/validate",
        { code, unit_id: unitId, lead_id: leadId || null });
      const line = res.data.data?.line || {};
      setCoupon({ ok: true, text: `${res.data.data?.coupon?.name} — potongan ${formatIDR(line.amount)}` });
    } catch (e) {
      setCoupon({ ok: false, text: e?.response?.data?.detail || "Kupon tidak berlaku." });
    }
  };

  const ruleLabel = (r) => `${r.name} · ${r.kind === "percent" ? `${r.value}%` : formatIDR(r.value)}`
    + (r.target && r.target !== "price" ? ` · potong ${r.target_label || r.target}` : "")
    + (r.requires_approval ? " · perlu persetujuan" : "");

  return (
    <>
      <div className="space-y-1.5">
        <Label>Skema pembayaran</Label>
        <Select value={form.scheme_id} onValueChange={(v) => set({ scheme_id: v })}>
          <SelectTrigger data-testid={ids.schemeSelect} aria-label="Skema pembayaran">
            <SelectValue placeholder="Pakai skema bawaan" />
          </SelectTrigger>
          <SelectContent>
            {schemes.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label>Tambahan (add-on) dari master</Label>
        <div className="flex gap-2">
          <Select value={addonPick} onValueChange={setAddonPick}>
            <SelectTrigger data-testid={ids.addonSelect} aria-label="Tambahan add-on">
              <SelectValue placeholder={addonMaster.length ? "Pilih tambahan"
                : "Master add-on belum ada"} />
            </SelectTrigger>
            <SelectContent>
              {addonMaster.map((a) => (
                <SelectItem key={a.code} value={a.code}>
                  {a.name} · {addonPriceLabel(a)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="button" variant="secondary" data-testid={ids.addonAddBtn}
            onClick={addAddon}><Plus className="h-4 w-4" /></Button>
        </div>
        {form.addons.map((a, i) => {
          const m = addonMaster.find((x) => x.code === a.code) || a;
          const sub = addonSubtotal(m, a.qty);
          return (
          <div key={a.code} data-testid="pricing-addon-row" data-addon-code={a.code}
            className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 rounded-md border bg-card px-2 py-1.5 shadow-[var(--shadow-card)]">
            <div className="min-w-0">
              <p className="truncate text-sm">{a.name || a.code}</p>
              <p className={`text-[11px] ${Number(m.unit_price) ? "text-muted-foreground" : "text-amber-700"}`}>{addonPriceLabel(m)}</p>
            </div>
            <Input type="number" min="0.1" step="0.1" value={a.qty} disabled={!isQtyMode(m)} title={isQtyMode(m) ? `Volume (${m.uom || "unit"})` : "Harga tetap per unit"}
              aria-label={`Volume tambahan ${a.name || a.code}`} className="w-20"
              onChange={(e) => {
                const next = [...form.addons];
                next[i] = { ...a, qty: e.target.value };
                set({ addons: next });
              }} />
            <span data-testid="pricing-addon-subtotal" data-addon-code={a.code} className="w-28 text-right text-sm font-semibold tabular-nums">
              {sub == null ? "— sesuai harga" : formatIDR(sub)}
            </span>
            <Button type="button" size="sm" variant="ghost"
              aria-label={`Hapus tambahan ${a.name || a.code}`}
              onClick={() => set({ addons: form.addons.filter((x) => x.code !== a.code) })}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
          );
        })}
        {form.addons.some((a) => !Number((addonMaster.find((x) => x.code === a.code) || {}).unit_price)) ? (
          <p data-testid="pricing-addon-price-warning" className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
            Ada add-on yang harganya masih Rp 0 di master. Isi harganya di <strong>Pusat Konfigurasi › Add-on</strong> agar
            masuk ke penawaran, SPR, dan komponen pembayaran — jangan simpan dengan Rp 0.
          </p>
        ) : null}
        {form.addons.length ? (
          <p className="text-right text-xs text-muted-foreground">
            Subtotal add-on: <strong data-testid="pricing-addon-total">{formatIDR(form.addons.reduce((t, a) => t + (addonSubtotal(addonMaster.find((x) => x.code === a.code) || a, a.qty) || 0), 0))}</strong>
            {form.addons.some((a) => (addonMaster.find((x) => x.code === a.code) || {}).pricing_mode === "percent_of_price") ? " + add-on persentase (dihitung mesin)" : ""}
          </p>
        ) : null}
      </div>

      {showCosts ? (
        <AllinSchemeField value={form.allin} unitId={unitId} price={price}
          onChange={(allin) => set({ allin })} />
      ) : null}

      <div className="rounded-lg border border-emerald-200/70 bg-emerald-50/40 p-3 space-y-2">
        <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-emerald-900">
          <TicketPercent className="h-3.5 w-3.5" /> Potongan dari aturan yang berlaku
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Skema diskon</Label>
            <Select value={form.discount_scheme_id || NONE}
              onValueChange={(v) => set({ discount_scheme_id: v === NONE ? "" : v })}
              disabled={!unitId}>
              <SelectTrigger data-testid={ids.discountSelect} aria-label="Skema diskon"
                className="bg-background">
                <SelectValue placeholder="Tanpa diskon" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Tanpa diskon</SelectItem>
                {rules.discount_schemes.map((r) => (
                  <SelectItem key={r.id} value={r.id}>{ruleLabel(r)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Promo</Label>
            <Select value={form.promo_id || NONE}
              onValueChange={(v) => set({ promo_id: v === NONE ? "" : v })} disabled={!unitId}>
              <SelectTrigger data-testid={ids.promoSelect} aria-label="Promo"
                className="bg-background">
                <SelectValue placeholder="Tanpa promo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Tanpa promo</SelectItem>
                {rules.promos.map((r) => (
                  <SelectItem key={r.id} value={r.id}>{ruleLabel(r)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.couponInput}>Kode kupon</Label>
          <div className="flex gap-2">
            <Input id={ids.couponInput} data-testid={ids.couponInput} className="bg-background uppercase"
              value={form.coupon_code || ""} placeholder="Mis. SIPRO2026"
              onChange={(e) => { set({ coupon_code: e.target.value.toUpperCase() }); setCoupon(null); }} />
            <Button type="button" variant="secondary" data-testid={ids.couponCheckBtn}
              onClick={checkCoupon}>Cek</Button>
          </div>
          {coupon ? (
            <p data-testid={ids.couponState}
              className={`flex items-center gap-1.5 text-xs ${coupon.ok ? "text-emerald-700" : "text-rose-700"}`}>
              {coupon.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
              {coupon.text}
            </p>
          ) : null}
        </div>
        {!unitId ? (
          <p className="text-xs text-muted-foreground">Pilih unit dulu untuk melihat diskon & promo yang berlaku.</p>
        ) : (!rules.discount_schemes.length && !rules.promos.length ? (
          <p className="text-xs text-muted-foreground">
            Belum ada skema diskon/promo yang berlaku untuk unit ini — atur di Pusat Konfigurasi › Harga & Promo.
          </p>
        ) : null)}
      </div>

      {showKpr ? (
        <div className="rounded-lg border bg-secondary/40 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Simulasi KPR (opsional)
          </p>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor={ids.kprTenor}>Tenor (bulan)</Label>
              <Input id={ids.kprTenor} type="number" data-testid={ids.kprTenor}
                className="bg-background" value={form.kpr.tenor_months}
                onChange={(e) => setKpr({ tenor_months: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.kprRate}>Bunga (% / tahun)</Label>
              <Input id={ids.kprRate} type="number" step="0.1" data-testid={ids.kprRate}
                className="bg-background" value={form.kpr.annual_rate_pct}
                onChange={(e) => setKpr({ annual_rate_pct: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.kprDp}>DP (%)</Label>
              <Input id={ids.kprDp} type="number" step="0.5" data-testid={ids.kprDp}
                className="bg-background" value={form.kpr.dp_pct}
                onChange={(e) => setKpr({ dp_pct: e.target.value })} />
            </div>
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Dibiarkan kosong = simulasi ditulis “belum ada data” (bukan Rp 0).
          </p>
        </div>
      ) : null}
    </>
  );
}

export const COST_FIELDS = [
  ["bphtb", "BPHTB"], ["notary_fee", "Biaya notaris / akad"],
  ["bank_fee", "Biaya bank (provisi, admin, materai)"], ["insurance", "Asuransi jiwa & kebakaran"],
];
export const costsTotal = (c) => COST_FIELDS.reduce((t, [k]) => t + (Number(c?.[k]) || 0), 0);
const isQtyMode = (m) => m && !["lump_sum", "percent_of_price"].includes(m.pricing_mode || "lump_sum");
export const addonPriceLabel = (m) => {
  if (!m) return "";
  if (!Number(m.unit_price)) return "harga belum diisi di master";
  if (m.pricing_mode === "percent_of_price") return `${m.unit_price}% × harga unit`;
  if (isQtyMode(m)) return `${formatIDR(m.unit_price)} / ${m.uom || "unit"}`;
  return formatIDR(m.unit_price || 0);
};
export const addonSubtotal = (m, qty) => {
  if (!m || m.pricing_mode === "percent_of_price") return null;
  const q = isQtyMode(m) ? (Number(qty) || 1) : 1;
  return Math.round((Number(m.unit_price) || 0) * q);
};
export const costsPayload = (c) => {
  if (!c) return null;
  const out = {};
  COST_FIELDS.forEach(([k]) => { if (c[k] !== "" && c[k] != null) out[k] = Number(c[k]); });
  if (c.all_in_by_developer) out.all_in_by_developer = true;
  return Object.keys(out).length ? out : null;
};

export const pricingPayload = (form) => ({
  scheme_id: form.scheme_id || null,
  addons: form.addons.map((a) => ({ code: a.code, qty: Number(a.qty) || 1 })),
  discount_scheme_id: form.discount_scheme_id || null,
  promo_id: form.promo_id || null,
  coupon_code: (form.coupon_code || "").trim() || null,
  kpr: {
    tenor_months: form.kpr.tenor_months === "" ? null : Number(form.kpr.tenor_months),
    annual_rate_pct: form.kpr.annual_rate_pct === "" ? null : Number(form.kpr.annual_rate_pct),
    dp_pct: form.kpr.dp_pct === "" ? null : Number(form.kpr.dp_pct),
  },
});

export const EMPTY_PRICING = {
  scheme_id: "", addons: [], discount_scheme_id: "", promo_id: "", coupon_code: "",
  kpr: { tenor_months: "", annual_rate_pct: "", dp_pct: "" },
  costs: {}, allin: { scheme_id: "", manual: false, items: [], reason: "" },
};
