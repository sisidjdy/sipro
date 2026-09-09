import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
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
import { PETTY } from "@/constants/testIds";

const blank = () => ({ key: Math.random().toString(36).slice(2), category: "transport",
  description: "", amount: "" });

/**
 * Pertanggungjawaban kas bon: rincian pengeluaran per kategori.
 * Sisa uang / kekurangan dihitung otomatis agar kasir tidak salah hitung.
 */
export default function SettleAdvanceDialog({ advance, onClose, onSaved }) {
  const [items, setItems] = useState([blank()]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (advance) { setItems([blank()]); setNote(""); setErr(""); }
  }, [advance]);

  const disbursed = Number(advance?.disbursed_amount || 0);
  const total = useMemo(
    () => items.reduce((s, i) => s + (Number(i.amount) || 0), 0), [items]);
  const returned = Math.max(0, disbursed - total);
  const reimburse = Math.max(0, total - disbursed);

  if (!advance) return null;

  const setItem = (key, patch) =>
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, ...patch } : i)));

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post(`/petty-cash/advances/${advance.id}/settle`, {
        items: items.filter((i) => Number(i.amount) > 0).map((i) => ({
          category: i.category, description: i.description, amount: Number(i.amount),
        })),
        note: note || null,
      });
      toast.success(`Pertanggungjawaban kas bon ${advance.no} tersimpan.`);
      onClose(); onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal menyimpan pertanggungjawaban.");
    } finally { setSaving(false); }
  };

  const valid = items.some((i) => Number(i.amount) > 0 && i.description.trim().length >= 2);

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent data-testid={PETTY.settleDialog} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Pertanggungjawaban Kas Bon {advance.no}</DialogTitle>
          <DialogDescription>
            Dicairkan {formatIDR(disbursed)}. Rincian pengeluaran akan dibukukan sebagai
            beban/WIP sesuai kategori, dan akun uang muka karyawan kembali nol.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-2">
            {items.map((i, idx) => (
              <div key={i.key} data-testid={PETTY.settleItemRow}
                className="grid grid-cols-12 items-end gap-2 rounded-lg border bg-secondary/30 p-2">
                <div className="col-span-4 space-y-1">
                  {idx === 0 ? <Label>Kategori</Label> : null}
                  <ReferenceSelect group="cashbon_category" value={i.category}
                    onChange={(v) => setItem(i.key, { category: v })}
                    testId={PETTY.settleItemCategory} />
                </div>
                <div className="col-span-5 space-y-1">
                  {idx === 0 ? <Label htmlFor={`desc-${i.key}`}>Uraian pengeluaran</Label> : null}
                  <Input id={`desc-${i.key}`} data-testid={PETTY.settleItemDesc}
                    value={i.description} placeholder="Mis. BBM & parkir"
                    onChange={(e) => setItem(i.key, { description: e.target.value })} />
                </div>
                <div className="col-span-2 space-y-1">
                  {idx === 0 ? <Label htmlFor={`amt-${i.key}`}>Jumlah (Rp)</Label> : null}
                  <RupiahInput id={`amt-${i.key}`} data-testid={PETTY.settleItemAmount} value={i.amount}
                    onChange={(e) => setItem(i.key, { amount: e.target.value })} />
                </div>
                <div className="col-span-1">
                  <Button type="button" size="icon" variant="ghost" aria-label="Hapus baris"
                    disabled={items.length === 1}
                    onClick={() => setItems((p) => p.filter((x) => x.key !== i.key))}>
                    <Trash2 className="h-4 w-4 text-rose-600" />
                  </Button>
                </div>
              </div>
            ))}
            <Button type="button" size="sm" variant="secondary" data-testid={PETTY.settleAddItem}
              onClick={() => setItems((p) => [...p, blank()])}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Tambah baris
            </Button>
          </div>

          <div className="grid grid-cols-3 gap-3 rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
            <div>
              <p className="text-xs text-muted-foreground">Total realisasi</p>
              <p data-testid={PETTY.settleTotal} className="font-semibold tabular-nums">
                {formatIDR(total)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Sisa dikembalikan</p>
              <p data-testid={PETTY.settleReturned}
                className="font-semibold tabular-nums text-emerald-700">{formatIDR(returned)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Penggantian (kelebihan pakai)</p>
              <p className="font-semibold tabular-nums text-amber-700">{formatIDR(reimburse)}</p>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="pc-settle-note">Catatan</Label>
            <Textarea id="pc-settle-note" value={note} rows={2}
              placeholder="Mis. sisa dikembalikan tunai ke kasir"
              onChange={(e) => setNote(e.target.value)} />
          </div>
          {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button data-testid={PETTY.settleSubmit} disabled={!valid || saving} onClick={submit}>
            {saving ? "Menyimpan…" : "Simpan Pertanggungjawaban"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
