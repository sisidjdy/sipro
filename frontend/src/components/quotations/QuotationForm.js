import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import QuotationBreakdown from "@/components/quotations/QuotationBreakdown";
import PricingFields, { EMPTY_PRICING, pricingPayload } from "@/components/pricing/PricingFields";
import api from "@/services/apiClient";
import { QUOTE, QUOTE_PRICING } from "@/constants/testIds";

const EMPTY = { unit_id: "", discount_reason: "", valid_days: "", note: "", ...EMPTY_PRICING };
const IDS = { ...QUOTE, ...QUOTE_PRICING };

/**
 * QuotationForm — buat/revisi penawaran dengan SIMULASI dulu.
 *
 * Fase 69: potongan TIDAK diketik bebas — skema diskon/promo/kupon dipilih dari aturan yang
 * dikonfigurasi (PricingFields), dan field yang sama dipakai dialog reservasi langsung.
 */
export default function QuotationForm({ open, onOpenChange, leadId, source, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [units, setUnits] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [addonMaster, setAddonMaster] = useState([]);
  const [calc, setCalc] = useState(null);
  const [simBusy, setSimBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setError(""); setCalc(null);
    setForm(source ? {
      unit_id: source.unit_id || "", scheme_id: source.scheme?.id || "",
      discount_scheme_id: source.discount_scheme?.rule_id || "",
      promo_id: source.promo?.rule_id || "", coupon_code: source.coupon_code || "",
      discount_reason: source.discount_reason || "", valid_days: source.valid_days || "",
      note: source.note || "",
      kpr: {
        tenor_months: source.kpr?.tenor_months || "",
        annual_rate_pct: source.kpr?.annual_rate_pct || "",
        dp_pct: source.kpr?.dp_pct || "",
      },
      addons: (source.addons || []).map((a) => ({ code: a.code, qty: a.qty || 1, name: a.name })),
    } : EMPTY);
    api.get("/quotations/options").then((o) => {
      const d = o.data.data || {};
      const list = d.units || [];
      setUnits(source?.unit_id && !list.some((x) => x.id === source.unit_id)
        ? [{ id: source.unit_id, code: source.unit_code, price: source.base_price }, ...list]
        : list);
      setSchemes(d.schemes || []);
      setAddonMaster(d.addons || []);
    }).catch((e) => setError(e?.response?.data?.detail || "Gagal memuat data master."));
  }, [open, source]);

  const payload = () => ({ unit_id: form.unit_id, lead_id: leadId, ...pricingPayload(form) });

  const simulate = async () => {
    if (!form.unit_id) { setError("Pilih unit lebih dulu."); return; }
    setSimBusy(true); setError("");
    try {
      const res = await api.post("/quotations/simulate", payload());
      setCalc(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal menghitung simulasi.");
    } finally { setSimBusy(false); }
  };

  const save = async () => {
    if (!form.unit_id) { setError("Pilih unit lebih dulu."); return; }
    setBusy(true); setError("");
    try {
      const body = {
        ...payload(),
        valid_days: form.valid_days === "" ? null : Number(form.valid_days),
        note: form.note.trim() || null,
        discount_reason: form.discount_reason.trim() || null,
      };
      const res = source?.id
        ? await api.post(`/quotations/${source.id}/revise`, body)
        : await api.post("/quotations", body);
      toast.success(res.data.message || "Penawaran tersimpan.");
      onOpenChange(false);
      onDone?.(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal menyimpan penawaran.");
    } finally { setBusy(false); }
  };

  const set = (patch) => { setForm((f) => ({ ...f, ...patch })); setCalc(null); };
  const setKpr = (patch) => { setForm((f) => ({ ...f, kpr: { ...f.kpr, ...patch } })); setCalc(null); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={QUOTE.dialog} className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {source?.id ? `Revisi penawaran ${source.no}` : "Buat penawaran harga"}
          </DialogTitle>
          <DialogDescription>
            Harga, potongan, termin, dan simulasi KPR dihitung SERVER dari master yang sama
            dengan tagihan — tidak ada rumus kedua, tidak ada diskon ketikan.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Unit yang ditawarkan</Label>
              <Select value={form.unit_id} onValueChange={(v) => set({ unit_id: v })}>
                <SelectTrigger data-testid={QUOTE.unitSelect} aria-label="Unit yang ditawarkan">
                  <SelectValue placeholder="Pilih unit tersedia" />
                </SelectTrigger>
                <SelectContent>
                  {units.map((u) => (
                    <SelectItem key={u.id} value={u.id}>{u.code}{u.type ? ` · ${u.type}` : ""}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <PricingFields form={form} set={set} setKpr={setKpr} unitId={form.unit_id}
              leadId={leadId} schemes={schemes} addonMaster={addonMaster} ids={IDS} />

            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="q-valid">Masa berlaku (hari)</Label>
                <Input id="q-valid" type="number" value={form.valid_days} placeholder="7"
                  onChange={(e) => set({ valid_days: e.target.value })} />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="q-disc-reason">Alasan diskon (wajib bila perlu persetujuan)</Label>
              <Textarea id="q-disc-reason" rows={2} data-testid={QUOTE.discountReason}
                value={form.discount_reason}
                placeholder="Mis. pembeli membandingkan dengan kompetitor; margin masih sehat."
                onChange={(e) => set({ discount_reason: e.target.value })} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="q-note">Catatan untuk pembeli</Label>
              <Textarea id="q-note" rows={2} value={form.note}
                onChange={(e) => set({ note: e.target.value })} />
            </div>
          </div>

          <div className="space-y-3">
            <Button type="button" variant="secondary" className="w-full"
              data-testid={QUOTE.simulateBtn} disabled={simBusy} onClick={simulate}>
              <RefreshCw className={`mr-1.5 h-4 w-4 ${simBusy ? "animate-spin" : ""}`} />
              Hitung simulasi
            </Button>
            {error ? (
              <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
            ) : null}
            {calc ? <QuotationBreakdown calc={calc} /> : (
              <p className="rounded-lg border border-dashed bg-card p-4 text-sm text-muted-foreground">
                Tekan “Hitung simulasi” untuk melihat rincian harga, potongan, termin, dan
                angsuran KPR sebelum penawaran disimpan.
              </p>
            )}
            {calc?.needs_discount_approval ? (
              <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Potongan {calc.discount_pct}% memerlukan persetujuan manajer
                (batas sales {calc.discount_limit_pct}% atau skema bertanda “perlu persetujuan”) —
                penawaran akan berstatus <b>menunggu persetujuan</b> dan alasan diskon wajib diisi.
              </p>
            ) : null}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={QUOTE.submitBtn} disabled={busy} onClick={save}>
            {busy ? "Menyimpan…" : (source?.id ? "Simpan revisi" : "Simpan penawaran")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
