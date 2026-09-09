import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ASSETS } from "@/constants/testIds";

/** Pelepasan aset: hitung laba/rugi otomatis dari nilai buku sebelum posting. */
export default function DisposeAssetDialog({ asset, onClose, onSaved }) {
  const [proceeds, setProceeds] = useState("0");
  const [source, setSource] = useState("bank");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (asset) { setProceeds("0"); setSource("bank"); setDate(""); setNote(""); setErr(""); }
  }, [asset]);

  if (!asset) return null;
  const bookValue = Number(asset.book_value || 0);
  const gain = (Number(proceeds) || 0) - bookValue;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post(`/fixed-assets/assets/${asset.id}/dispose`, {
        proceeds: Number(proceeds) || 0, source,
        date: date ? new Date(date).toISOString() : null, note: note || null,
      });
      toast.success(`Aset ${asset.code} dilepas dan dibukukan.`);
      onClose(); onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal membukukan pelepasan aset.");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent data-testid={ASSETS.disposeDialog} className="max-w-md">
        <DialogHeader>
          <DialogTitle>Lepas / Jual Aset {asset.code}</DialogTitle>
          <DialogDescription>
            {asset.name} · nilai buku saat ini {formatIDR(bookValue)}. Harga perolehan dan
            akumulasi penyusutannya akan dihapus dari neraca.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="as-proceeds">Hasil penjualan (Rp)</Label>
            <RupiahInput id="as-proceeds" data-testid={ASSETS.disposeProceeds}
              value={proceeds} onChange={(e) => setProceeds(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Kas penerimaan</Label>
            <ReferenceSelect group="cash_source" value={source} onChange={setSource}
              testId={ASSETS.disposeSource} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-dispose-date">Tanggal pelepasan</Label>
            <Input id="as-dispose-date" data-testid={ASSETS.disposeDate} type="date" value={date}
              onChange={(e) => setDate(e.target.value)} />
          </div>
          <div data-testid={ASSETS.disposeGainPreview}
            className={`rounded-lg border p-3 text-sm ${gain >= 0 ? "bg-emerald-50" : "bg-rose-50"}`}>
            {gain >= 0 ? "Laba pelepasan" : "Rugi pelepasan"}:{" "}
            <span className="font-semibold tabular-nums">{formatIDR(Math.abs(gain))}</span>
            <p className="mt-1 text-xs text-muted-foreground">
              {gain >= 0 ? "Dikreditkan ke 4-1300 Laba Pelepasan Aset."
                : "Didebitkan ke 6-1800 Kerugian Pelepasan Aset."}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="as-dispose-note">Catatan</Label>
            <Textarea id="as-dispose-note" value={note} rows={2}
              placeholder="Mis. dijual ke pihak ketiga"
              onChange={(e) => setNote(e.target.value)} />
          </div>
          {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button data-testid={ASSETS.disposeSubmit} disabled={saving} onClick={submit}>
            {saving ? "Memproses…" : "Bukukan Pelepasan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
