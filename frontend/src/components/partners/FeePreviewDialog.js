import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Calculator, CheckCircle2 } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import MoneyText from "@/components/patterns/MoneyText";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { PARTNERS } from "@/constants/testIds";

/**
 * FeePreviewDialog — pratinjau perhitungan fee memakai MESIN YANG SAMA dengan pemicu
 * otomatis (`POST /partners/rules/preview` → `partner_engine.compute`).
 *
 * Kenapa ini bukan hiasan: sebelum Fase 42 tidak ada cara memeriksa "kalau deal ini PPJB,
 * mitra dapat berapa?" tanpa benar-benar menerbitkan tagihan. Kalau ditolak, alasannya
 * ditampilkan apa adanya (aturan bentrok / kontrak habis / porsi 0%) supaya bisa dibetulkan.
 */
export default function FeePreviewDialog({ context, open, onOpenChange, onDone }) {
  const { can } = useAuth();
  // Izin diambil dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis
  // ulang di layar. Matriks RBAC bisa diubah admin lewat Pusat Konfigurasi; daftar peran
  // hardcode membuat tombol berbeda dengan jawaban server — tombol mati (403) atau
  // tombol yang seharusnya ada tapi hilang.
  // Menerbitkan tagihan = MENGAJUKAN, bukan menyetujui: izinnya `marketing_fee:create`.
  // Daftar peran lama memasukkan finance, padahal finance-lah yang menyetujui —
  // tombolnya selalu dijawab 403 oleh server.
  const canIssue = can("marketing_fee", "create");
  const [partners, setPartners] = useState([]);
  const [deals, setDeals] = useState([]);
  const [partnerId, setPartnerId] = useState("");
  const [dealId, setDealId] = useState("");
  const [trigger, setTrigger] = useState("ppjb_signed");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setPartnerId(context?.partnerId || "");
    api.get("/partners", { params: { limit: 200 } })
      .then((r) => setPartners(r.data.data || [])).catch(() => setPartners([]));
    api.get("/deals", { params: { limit: 100 } })
      .then((r) => setDeals(r.data.data || [])).catch(() => setDeals([]));
  }, [open, context]);

  const run = async () => {
    if (!partnerId || !dealId) {
      toast.error("Pilih mitra dan deal terlebih dulu."); return;
    }
    setBusy(true);
    try {
      const res = await api.post("/partners/rules/preview", {
        partner_id: partnerId, deal_id: dealId, trigger,
      });
      setResult(res.data.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghitung pratinjau.");
    } finally { setBusy(false); }
  };

  const issue = async () => {
    setBusy(true);
    try {
      const res = await api.post("/partners/rules/issue", {
        partner_id: partnerId, deal_id: dealId, trigger,
      });
      toast.success(`Tagihan fee ${res.data.data.fee.no} diterbitkan `
        + "dan menunggu persetujuan finance.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerbitkan tagihan fee.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PARTNERS.previewDialog} className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Pratinjau Perhitungan Fee Mitra</DialogTitle>
          <DialogDescription>
            Angka di bawah dihitung mesin yang sama dengan pemicu otomatis — jadi yang
            terlihat di sini persis yang akan dibukukan.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Mitra</Label>
            <Select value={partnerId} onValueChange={setPartnerId}>
              <SelectTrigger data-testid={PARTNERS.previewPartner} aria-label="Mitra">
                <SelectValue placeholder="Pilih mitra" />
              </SelectTrigger>
              <SelectContent>
                {partners.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name} ({p.status})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Deal / unit</Label>
            <Select value={dealId} onValueChange={setDealId}>
              <SelectTrigger data-testid={PARTNERS.previewDeal} aria-label="Deal">
                <SelectValue placeholder="Pilih deal" />
              </SelectTrigger>
              <SelectContent>
                {deals.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.unit_code || d.id.slice(0, 8)} · {d.status} · Rp{" "}
                    {Number(d.price || 0).toLocaleString("id-ID")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Pemicu</Label>
            <ReferenceSelect group="partner_fee_trigger" value={trigger} onChange={setTrigger}
              testId={PARTNERS.previewTrigger} />
          </div>

          <Button data-testid={PARTNERS.previewRun} onClick={run} disabled={busy}
            className="w-full">
            <Calculator className="mr-1.5 h-4 w-4" />
            {busy ? "Menghitung…" : "Hitung"}
          </Button>

          {result ? (
            <div data-testid={PARTNERS.previewResult}
              className="space-y-2 rounded-md border bg-secondary/40 p-3 text-sm">
              {result.ok ? (
                <>
                  <p className="flex items-center gap-1.5 font-medium text-emerald-700">
                    <CheckCircle2 className="h-4 w-4" /> Aturan {result.rule?.code} dipakai
                  </p>
                  <p className="text-xs text-muted-foreground">{result.rule?.name}</p>
                  <dl className="grid grid-cols-2 gap-1.5">
                    <dt className="text-muted-foreground">Hasil aturan (100%)</dt>
                    <dd className="text-right"><MoneyText value={result.gross_full} /></dd>
                    <dt className="text-muted-foreground">Porsi pemicu ini</dt>
                    <dd className="text-right tabular-nums">{result.share_pct}%</dd>
                    <dt className="text-muted-foreground">Beban (bruto dibukukan)</dt>
                    <dd className="text-right"><MoneyText value={result.amounts?.expense} /></dd>
                    <dt className="text-muted-foreground">
                      PPh ({result.tax?.pph_type} {result.tax?.pph_pct}%)
                    </dt>
                    <dd className="text-right"><MoneyText value={result.amounts?.pph} /></dd>
                    <dt className="font-medium">Diterima mitra (netto)</dt>
                    <dd className="text-right font-medium">
                      <MoneyText value={result.amounts?.payout} />
                    </dd>
                    <dt className="text-muted-foreground">Persen dari harga jual</dt>
                    <dd className="text-right tabular-nums">
                      {result.fee_pct_of_price ?? "—"}% (pagar {result.guard_pct}%)
                    </dd>
                  </dl>
                  {result.needs_owner_approval ? (
                    <p className="flex items-start gap-1.5 text-xs font-medium text-amber-700">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      Melewati pagar wajar — tagihan akan ditandai butuh persetujuan owner.
                    </p>
                  ) : null}
                </>
              ) : (
                <p className="flex items-start gap-1.5 text-amber-800">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {result.reason}
                </p>
              )}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Tutup
          </Button>
          {result?.ok && canIssue ? (
            <Button data-testid={PARTNERS.previewIssue} onClick={issue} disabled={busy}>
              Terbitkan tagihan fee
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
