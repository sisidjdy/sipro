import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import QuotationBreakdown from "@/components/quotations/QuotationBreakdown";
import PricingFields, { EMPTY_PRICING, pricingPayload } from "@/components/pricing/PricingFields";
import { allinPayload } from "@/components/pricing/AllinSchemeField";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { DEALS, P75, RESERVE } from "@/constants/testIds";

/**
 * ReserveDialog — reservasi langsung dengan BREAKDOWN yang sama dengan penawaran.
 *
 * Cacat yang ditutup (Fase 69): dulu dialog ini hanya meminta booking fee, sehingga deal
 * lahir tanpa add-on/diskon/termin — tidak sinkron dengan penawaran. Kini harga dihitung
 * mesin yang sama (`/quotations/simulate`) dan rinciannya tersimpan pada deal.
 */
export default function ReserveDialog({
  mode = "byLead", leadId, leadName, unitId, unitLabel, open, onOpenChange, onReserved,
}) {
  const [options, setOptions] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [addonMaster, setAddonMaster] = useState([]);
  const [choice, setChoice] = useState("");
  const [form, setForm] = useState({ ...EMPTY_PRICING, booking_fee: "" });
  const [calc, setCalc] = useState(null);
  const [error, setError] = useState("");
  const [simBusy, setSimBusy] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setChoice(""); setCalc(null); setError("");
    setForm({ ...EMPTY_PRICING, booking_fee: "" });
    (async () => {
      try {
        const [o, extra] = await Promise.all([
          api.get("/quotations/options"),
          mode === "byLead" ? Promise.resolve(null) : api.get("/leads", { params: { limit: 200 } }),
        ]);
        const d = o.data.data || {};
        setSchemes(d.schemes || []); setAddonMaster(d.addons || []);
        setOptions(mode === "byLead" ? (d.units || []) : (extra?.data?.data || []));
        const fee = await api.get("/settings/effective", { params: { keys: "booking_fee.default_amount" } }).catch(() => null);
        const v = fee?.data?.data?.["booking_fee.default_amount"];
        if (v != null) setForm((f) => ({ ...f, booking_fee: String(v) }));
      } catch (e) {
        setOptions([]); setError(e?.response?.data?.detail || "Gagal memuat data master.");
      }
    })();
  }, [open, mode]);

  const unit = mode === "byLead" ? choice : unitId;
  const lead = mode === "byLead" ? leadId : choice;
  const { user, can } = useAuth();
  const [stale, setStale] = useState(false);
  const [zeroOverride, setZeroOverride] = useState({ reason: "", prices: {} });
  const mayOverrideZero = can("pricing", "approve");
  const zeroAddons = (form.addons || []).filter((a) => !Number((addonMaster.find((x) => x.code === a.code) || {}).unit_price));
  const unitPrice = Number((options.find((o) => o.id === unit) || {}).price) || calc?.net_price || 0;
  const allinPreview = form.allin?.preview;
  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }));
    if (patch.allin && Object.keys(patch).length === 1) { setStale(!!calc); return; }
    setCalc(null); setStale(false);
  };
  const setKpr = (patch) => { setForm((f) => ({ ...f, kpr: { ...f.kpr, ...patch } })); setCalc(null); };

  const simulate = async () => {
    if (!unit) { setError("Pilih unit lebih dulu."); return; }
    setSimBusy(true); setError("");
    try {
      const res = await api.post("/quotations/simulate",
        { unit_id: unit, lead_id: lead || null, ...pricingPayload(form), ...allinPayload(form.allin),
          booking_fee: form.booking_fee === "" || form.booking_fee == null ? null : Number(form.booking_fee) || 0 });
      setCalc(res.data.data); setStale(false);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal menghitung simulasi.");
    } finally { setSimBusy(false); }
  };

  const submit = async () => {
    if (!unit || !lead) { toast.error("Lengkapi pilihan terlebih dahulu."); return; }
    setBusy(true); setError("");
    try {
      const res = await api.post("/deals/reserve", {
        unit_id: unit, lead_id: lead, booking_fee: Number(form.booking_fee) || 0,
        ...pricingPayload(form), ...allinPayload(form.allin),
        limit_override_reason: form.limit_override_reason || undefined,
        addon_zero_override: zeroAddons.length ? {
          reason: zeroOverride.reason,
          prices: Object.fromEntries(Object.entries(zeroOverride.prices).map(([k, v]) => [k, Number(v) || 0])),
        } : undefined,
      });
      toast.success("Unit berhasil di-reserve (hold aktif) — rincian harga tersimpan.");
      onOpenChange(false);
      onReserved && onReserved(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal membuat reservasi.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={RESERVE.dialog} className="max-h-[94vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Buat Reservasi (SPR)</DialogTitle>
          <DialogDescription>
            {mode === "byLead"
              ? `Pesan unit tersedia untuk lead ${leadName || ""}.`
              : `Pilih lead untuk unit ${unitLabel || ""}.`}
            {" "}Harga dihitung mesin yang sama dengan penawaran.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>{mode === "byLead" ? "Unit Tersedia" : "Lead"}</Label>
              <Select value={choice} onValueChange={(v) => { setChoice(v); setCalc(null); }}>
                <SelectTrigger data-testid="reserve-choice-select"
                  aria-label={mode === "byLead" ? "Unit tersedia" : "Lead"}>
                  <SelectValue placeholder={mode === "byLead" ? "Pilih unit" : "Pilih lead"} />
                </SelectTrigger>
                <SelectContent>
                  {options.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {mode === "byLead" ? `${o.code} · ${o.type} · ${formatIDR(o.price)}` : `${o.name} · ${o.phone}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {mode === "byLead" && !options.length ? (
                <p className="text-xs text-muted-foreground">Tidak ada unit tersedia.</p>
              ) : null}
            </div>
            <PricingFields form={form} set={set} setKpr={setKpr} unitId={unit} leadId={lead}
              schemes={schemes} addonMaster={addonMaster} ids={RESERVE} showCosts price={unitPrice} />
            {zeroAddons.length ? (
              <div data-testid={P75.addonZeroOverride} className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                <p><strong>Reservasi diblokir</strong>: add-on {zeroAddons.map((a) => a.code).join(", ")} berharga Rp 0 di master.
                  {mayOverrideZero ? " Sebagai manajer Anda bisa mengisi harga + alasan — dicatat sebagai add-on berharga + diskon 100% (pendapatan & piutang utuh)."
                    : " Minta sales manager mengisi harga di master atau melakukan override."}</p>
                {mayOverrideZero ? (
                  <>
                    {zeroAddons.map((a) => (
                      <div key={a.code} className="flex items-center gap-2">
                        <span className="w-32 truncate">{a.name || a.code}</span>
                        <RupiahInput className="bg-background" placeholder="Harga (Rp)" data-testid={`addon-zero-price-${a.code}`}
                          value={zeroOverride.prices[a.code] || ""}
                          onChange={(e) => setZeroOverride((z) => ({ ...z, prices: { ...z.prices, [a.code]: e.target.value } }))} />
                      </div>
                    ))}
                    <Textarea data-testid={P75.addonZeroReason} rows={2} className="bg-background" placeholder="Alasan override (min. 10 huruf)"
                      value={zeroOverride.reason} onChange={(e) => setZeroOverride((z) => ({ ...z, reason: e.target.value }))} />
                  </>
                ) : null}
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="fee">Booking fee / tanda jadi (Rp)</Label>
              <RupiahInput id="fee" data-testid={RESERVE.bookingFee} value={form.booking_fee}
                onChange={(e) => setForm((f) => ({ ...f, booking_fee: e.target.value }))} />
              <p className="text-xs text-muted-foreground">Dibayar saat keep unit; dialihkan ke termin saat SPR sah — bukan potongan harga.</p>
            </div>
          </div>
          <div className="space-y-3 lg:sticky lg:top-0 lg:self-start">
            <Button type="button" variant="secondary" className="w-full"
              data-testid={RESERVE.simulateBtn} disabled={simBusy} onClick={simulate}>
              <RefreshCw className={`mr-1.5 h-4 w-4 ${simBusy ? "animate-spin" : ""}`} />
              Hitung rincian harga
            </Button>
            {error ? (
              <p data-testid={RESERVE.error}
                className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
            ) : null}
            {error && /batas/i.test(error) ? (
              <div className="space-y-1">
                <Label htmlFor="limit-override-reason" className="text-xs">Alasan melewati batas unit per lead (peran override, min. 10 huruf)</Label>
                <Textarea id="limit-override-reason" data-testid="reserve-limit-override-reason" rows={2} className="bg-background"
                  value={form.limit_override_reason || ""} onChange={(e) => setForm((f) => ({ ...f, limit_override_reason: e.target.value }))} />
              </div>
            ) : null}
            {calc ? (
              <div data-testid={RESERVE.breakdown}>
                {stale ? (
                  <p data-testid={P75.recalcHint} className="mb-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900">
                    Skema biaya berubah — tekan <b>Hitung rincian harga</b> lagi agar ringkasan biaya ikut diperbarui.
                  </p>
                ) : null}
                <QuotationBreakdown calc={calc} stale={stale} />
                {(() => {
                  // Pratinjau skema all-in hanya CADANGAN sebelum "Hitung rincian" ditekan ulang —
                  // angka resmi ada di komponen pembayaran hasil simulasi backend.
                  if (calc.costs || !allinPreview) return null;
                  const comps = allinPreview.components || [];
                  if (!comps.length) return null;
                  const buyer = comps.filter((c) => c.treatment !== "developer_borne").reduce((t, c) => t + (c.amount || 0), 0);
                  return (
                    <div data-testid={RESERVE.costsSummary} className="mt-2 rounded-lg border border-dashed bg-card p-3 text-sm">
                      <div className="flex justify-between"><span>Pratinjau biaya · {allinPreview.scheme_name}</span>
                        <strong data-testid="reserve-costs-total">{formatIDR(buyer)}</strong></div>
                      <ul className="mt-1 space-y-0.5 text-xs">
                        {comps.map((c) => (
                          <li key={c.code} data-testid="reserve-cost-row" data-code={c.code} className="flex justify-between gap-2">
                            <span className="text-muted-foreground">{c.name}{c.treatment === "developer_borne" ? " · developer" : ""}</span>
                            <span>{formatIDR(c.amount || 0)}</span>
                          </li>
                        ))}
                      </ul>
                      <p className="mt-1 text-[11px] text-amber-800">Belum termasuk potongan promo — tekan <b>Hitung rincian harga</b> untuk angka resmi.</p>
                    </div>
                  );
                })()}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed bg-card p-4 text-sm text-muted-foreground">
                Tekan “Hitung rincian harga” untuk melihat harga dasar, add-on, potongan, dan termin sebelum unit dikunci.
              </p>
            )}
            {calc?.needs_discount_approval ? (
              <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Potongan ini memerlukan persetujuan manajer — buat <b>penawaran</b> lebih dulu,
                lalu konversi menjadi reservasi setelah disetujui.
              </p>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={DEALS.reserveSubmit} onClick={submit}
            disabled={busy || !!calc?.needs_discount_approval}>
            {busy ? "Memproses..." : "Reservasi"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
