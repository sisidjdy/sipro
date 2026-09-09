import React, { useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/services/apiClient";
import { P53 } from "@/constants/testIds";

/**
 * CostsDialog — mengisi komponen biaya transaksi kontrak (BPHTB, notaris, bank, asuransi,
 * PPh, promo, plafon KPR).
 *
 * Aturan yang dipegang layar ini: **kolom yang dibiarkan kosong TIDAK menjadi 0.** Nol
 * berarti "biayanya memang tidak ada", dan pernyataan itu langsung tercetak di dokumen
 * legal. Karena itu kosong = "belum diisi", dan ada tombol khusus untuk MENGOSONGKAN
 * kembali nilai yang sudah pernah diisi (mengirim -1 ke server).
 */
const FIELDS = [
  { key: "bphtb", label: "BPHTB" },
  { key: "notary_fee", label: "Biaya notaris / akad" },
  { key: "bank_fee", label: "Biaya bank (KPR)", kprOnly: true },
  { key: "insurance", label: "Asuransi jiwa & kebakaran (KPR)", kprOnly: true },
  { key: "pph_seller", label: "PPh penjual" },
  { key: "promo_discount", label: "Promo / potongan all-in" },
  { key: "plafon_kredit", label: "Plafon kredit bank (KPR)", kprOnly: true },
];

export default function CostsDialog({ contract, open, onOpenChange, onSaved }) {
  const costs = contract?.costs || {};
  const [form, setForm] = useState(() => {
    const init = {};
    FIELDS.forEach((f) => { init[f.key] = costs[f.key] ?? ""; });
    return init;
  });
  const [busy, setBusy] = useState(false);
  const isKpr = contract?.scheme === "kpr";

  const save = async () => {
    const payload = {};
    FIELDS.forEach((f) => {
      if (f.kprOnly && !isKpr) return;
      const raw = String(form[f.key] ?? "").trim();
      if (raw === "") {
        // Kosong = TIDAK dikirim (nilai lama dibiarkan). Untuk menghapus nilai, pemakai
        // menekan tombol "Kosongkan" yang mengirim -1 secara sengaja.
        return;
      }
      const n = Number(raw.replace(/[^\d-]/g, ""));
      if (!Number.isNaN(n)) payload[f.key] = n;
    });
    if (!Object.keys(payload).length) {
      toast.error("Tidak ada nilai yang diubah.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post(`/contracts/${contract.id}/costs`, payload);
      toast.success("Komponen biaya kontrak diperbarui.");
      onOpenChange(false);
      onSaved && onSaved(res.data.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan komponen biaya.");
    } finally { setBusy(false); }
  };

  const clearField = async (key) => {
    setBusy(true);
    try {
      const res = await api.post(`/contracts/${contract.id}/costs`, { [key]: -1 });
      setForm((f) => ({ ...f, [key]: "" }));
      toast.success("Nilai dikosongkan kembali menjadi ‘belum diisi’.");
      onSaved && onSaved(res.data.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengosongkan nilai.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P53.costsDialog}
        className="max-h-[85vh] max-w-lg overflow-y-auto bg-background">
        <DialogHeader>
          <DialogTitle>Komponen biaya kontrak {contract?.number}</DialogTitle>
          <DialogDescription>
            Angka di sini yang tercetak pada SPR/SPKT. Kolom yang dibiarkan kosong akan
            ditulis “belum ditetapkan” di dokumen — <strong>bukan Rp 0</strong>.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {FIELDS.filter((f) => !f.kprOnly || isKpr).map((f) => (
            <div key={f.key} className="space-y-1.5">
              <Label htmlFor={`cost-${f.key}`}>{f.label}</Label>
              <div className="flex items-center gap-2">
                <Input id={`cost-${f.key}`} inputMode="numeric" className="bg-background"
                  aria-label={f.label}
                  placeholder={costs[f.key] == null ? "belum diisi" : ""}
                  value={form[f.key]}
                  onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))} />
                {costs[f.key] != null ? (
                  <Button type="button" size="sm" variant="ghost" disabled={busy}
                    onClick={() => clearField(f.key)}>Kosongkan</Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button data-testid={P53.costsSubmit} onClick={save} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
