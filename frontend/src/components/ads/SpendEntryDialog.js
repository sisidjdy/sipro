import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import api from "@/services/apiClient";
import { ADS } from "@/constants/testIds";
import { formatIDR } from "@/utils/formatters";

const RESULT_TEXT = {
  inserted: "Biaya tersimpan sebagai baris baru.",
  updated: "Biaya hari itu DIPERBARUI (nilai lama tersimpan di riwayat).",
  unchanged: "Angkanya sama dengan yang sudah tersimpan — tidak ada yang berubah.",
};

/**
 * SpendEntryDialog — entri biaya iklan harian secara manual.
 *
 * Untuk tim yang tidak mau berurusan dengan CSV. Bentuknya sengaja ringkas (tanggal,
 * kampanye, biaya) karena inilah yang diketik setiap hari; sisanya opsional.
 *
 * Kolom impresi/klik/lead SENGAJA boleh kosong dan disimpan sebagai “tidak dilaporkan”,
 * bukan 0 — CTR yang dihitung dari nol palsu akan menyesatkan.
 */
export default function SpendEntryDialog({ open, onOpenChange, campaigns = [], onDone }) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ campaign_id: "", date: today, spend: "", adset_name: "",
    impressions: "", clicks: "", leads_platform: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ campaign_id: campaigns[0]?.id || "", date: today, spend: "", adset_name: "",
        impressions: "", clicks: "", leads_platform: "" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  // Angka rupiah ditulis ulang berkelompok ribuan supaya bisa DIBACA sebelum disimpan;
  // parsing sebenarnya tetap di backend (`ads_engine.parse_amount`) supaya satu aturan saja.
  const spendNumber = Number(form.spend);
  const spendPreview = form.spend === ""
    ? "Wajib diisi — biaya hari itu dalam rupiah."
    : Number.isFinite(spendNumber) && spendNumber >= 0
      ? `Tersimpan sebagai ${formatIDR(spendNumber)}`
      : "Bukan angka yang sah.";

  const submit = async () => {
    if (!form.campaign_id) {
      toast.error("Pilih kampanye — biaya iklan harus punya pemilik.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post("/ads/spend", {
        campaign_id: form.campaign_id, date: form.date, spend: String(form.spend || ""),
        adset_name: form.adset_name || null,
        impressions: form.impressions === "" ? null : String(form.impressions),
        clicks: form.clicks === "" ? null : String(form.clicks),
        leads_platform: form.leads_platform === "" ? null : String(form.leads_platform),
      });
      toast.success(RESULT_TEXT[res.data.result] || "Biaya tersimpan.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan biaya iklan.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={ADS.spendForm}>
        <DialogHeader>
          <DialogTitle>Entri biaya iklan harian</DialogTitle>
          <DialogDescription>
            Satu kampanye hanya boleh punya satu angka per tanggal. Mengisi tanggal yang sama
            lagi akan memperbarui angkanya dan menyimpan nilai lama di riwayat.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Kampanye</Label>
            <Select value={form.campaign_id} onValueChange={set("campaign_id")}>
              <SelectTrigger data-testid={ADS.spendCampaign} aria-label="Kampanye">
                <SelectValue placeholder="Pilih kampanye…" />
              </SelectTrigger>
              <SelectContent>
                {campaigns.map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!campaigns.length ? (
              <p className="text-xs text-amber-700">
                Belum ada kampanye terdaftar — daftarkan dulu di tab Kampanye.
              </p>
            ) : null}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="sdate">Tanggal</Label>
              <Input id="sdate" type="date" max={today} data-testid={ADS.spendDate}
                value={form.date} onChange={(e) => set("date")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="samount">Biaya hari itu (Rp)</Label>
              <RupiahInput id="samount" data-testid={ADS.spendAmount} value={form.spend} placeholder="mis. 1250000"
                onChange={(e) => set("spend")(e.target.value)} />
              {/* Pratinjau nominal: kesalahan paling sering pada input rupiah adalah SATU NOL
                  kelebihan/kekurangan, dan angka telanjang "12500000" sulit dibaca mata.
                  Karena itu nilai yang akan tersimpan ditampilkan berkelompok ribuan. */}
              <p className="text-xs text-slate-500" data-testid={ADS.spendAmountPreview}>
                {spendPreview}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sadset">Nama ad set / grup iklan</Label>
              <Input id="sadset" data-testid={ADS.spendAdset} value={form.adset_name}
                placeholder="opsional" onChange={(e) => set("adset_name")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="simp">Impresi</Label>
              <Input id="simp" type="number" min="0" data-testid={ADS.spendImpressions}
                value={form.impressions} placeholder="kosongkan bila tidak tahu"
                onChange={(e) => set("impressions")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sclick">Klik</Label>
              <Input id="sclick" type="number" min="0" data-testid={ADS.spendClicks}
                value={form.clicks} placeholder="kosongkan bila tidak tahu"
                onChange={(e) => set("clicks")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="slead">Lead menurut platform</Label>
              <Input id="slead" type="number" min="0" data-testid={ADS.spendLeads}
                value={form.leads_platform} placeholder="kosongkan bila tidak tahu"
                onChange={(e) => set("leads_platform")(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={ADS.spendSubmit} onClick={submit}
            disabled={busy || !campaigns.length}>
            {busy ? "Menyimpan…" : "Simpan Biaya"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
