import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, X } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { FINANCE } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";

// ------------------------- Payment Scheme -------------------------
export function PaymentSchemeDialog({ open, onOpenChange, onDone }) {
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [items, setItems] = useState([{ label: "", basis: "percent", value: "", due_offset_days: "0" }]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setName(""); setIsDefault(false);
      setItems([{ label: "", basis: "percent", value: "", due_offset_days: "0" }]);
    }
  }, [open]);

  const setItem = (i, k, v) => setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, [k]: v } : it)));
  const addItem = () => setItems((prev) => [...prev, { label: "", basis: "percent", value: "", due_offset_days: "0" }]);
  const rmItem = (i) => setItems((prev) => prev.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!name.trim()) { toast.error("Nama skema wajib diisi."); return; }
    const clean = items
      .filter((it) => it.label.trim())
      .map((it) => ({
        label: it.label.trim(), basis: it.basis,
        value: Number(it.value) || 0, due_offset_days: Number(it.due_offset_days) || 0,
      }));
    if (!clean.length) { toast.error("Minimal satu termin diperlukan."); return; }
    setBusy(true);
    try {
      await api.post("/finance/config/payment-schemes", { name: name.trim(), items: clean, is_default: isDefault });
      toast.success("Skema pembayaran dibuat.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat skema."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Skema Pembayaran Baru</DialogTitle>
          <DialogDescription>Definisikan termin (persen dari harga atau nominal tetap) + offset jatuh tempo.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="psname">Nama Skema</Label>
            <Input id="psname" value={name} data-testid="payment-scheme-name"
              onChange={(e) => setName(e.target.value)} placeholder="mis. Standar KPR (DP 20%)" />
          </div>
          <div className="space-y-2">
            <Label>Termin</Label>
            {items.map((it, i) => (
              <div key={i} className="grid grid-cols-12 items-center gap-2">
                <Input className="col-span-4" placeholder="Label" value={it.label}
                  onChange={(e) => setItem(i, "label", e.target.value)} />
                <div className="col-span-3">
                  <Select value={it.basis} onValueChange={(v) => setItem(i, "basis", v)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <ReferenceItems group="scheme_basis" />
                    </SelectContent>
                  </Select>
                </div>
                {it.basis === "fixed" ? (
                  <RupiahInput className="col-span-2" placeholder="Nilai" value={it.value}
                    onChange={(e) => setItem(i, "value", e.target.value)} />
                ) : (
                  <Input className="col-span-2" type="number" placeholder="Nilai" value={it.value}
                    onChange={(e) => setItem(i, "value", e.target.value)} />
                )}
                <Input className="col-span-2" type="number" placeholder="Hari" value={it.due_offset_days}
                  onChange={(e) => setItem(i, "due_offset_days", e.target.value)} />
                <Button size="icon" variant="ghost" className="col-span-1 h-8 w-8 text-rose-600"
                  onClick={() => rmItem(i)} disabled={items.length <= 1}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button size="sm" variant="outline" onClick={addItem}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Tambah Termin
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="psdefault" checked={isDefault} onCheckedChange={setIsDefault} />
            <Label htmlFor="psdefault">Jadikan skema default</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FINANCE.paymentSchemeSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan\u2026" : "Simpan Skema"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------- Commission Scheme -------------------------
export function CommissionSchemeDialog({ open, onOpenChange, onDone }) {
  const [name, setName] = useState("");
  const [basis, setBasis] = useState("price");
  const [trigger, setTrigger] = useState("booked");
  const [isDefault, setIsDefault] = useState(false);
  const [tiers, setTiers] = useState([{ min_amount: "0", max_amount: "", rate_pct: "" }]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setName(""); setBasis("price"); setTrigger("booked"); setIsDefault(false);
      setTiers([{ min_amount: "0", max_amount: "", rate_pct: "" }]);
    }
  }, [open]);

  const setTier = (i, k, v) => setTiers((prev) => prev.map((t, idx) => (idx === i ? { ...t, [k]: v } : t)));
  const addTier = () => setTiers((prev) => [...prev, { min_amount: "", max_amount: "", rate_pct: "" }]);
  const rmTier = (i) => setTiers((prev) => prev.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!name.trim()) { toast.error("Nama skema wajib diisi."); return; }
    const clean = tiers
      .filter((t) => t.rate_pct !== "")
      .map((t) => ({
        min_amount: Number(t.min_amount) || 0,
        max_amount: t.max_amount === "" ? null : Number(t.max_amount),
        rate_pct: Number(t.rate_pct) || 0,
      }));
    if (!clean.length) { toast.error("Minimal satu tier diperlukan."); return; }
    setBusy(true);
    try {
      await api.post("/finance/config/commission-schemes", {
        name: name.trim(), basis, trigger, tiers: clean, is_default: isDefault,
      });
      toast.success("Skema komisi dibuat.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat skema komisi."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Skema Komisi Baru</DialogTitle>
          <DialogDescription>Bracket-based: tier yang mencakup basis dipilih, rate diterapkan ke seluruh basis.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="csname">Nama Skema</Label>
            <Input id="csname" value={name} data-testid="commission-scheme-name"
              onChange={(e) => setName(e.target.value)} placeholder="mis. Komisi Sales Bertingkat" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Basis</Label>
              <Select value={basis} onValueChange={setBasis}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <ReferenceItems group="commission_basis" />
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Trigger</Label>
              <Select value={trigger} onValueChange={setTrigger}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <ReferenceItems group="commission_trigger" only={["booked", "paid_off"]} />
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>Tier (bracket)</Label>
            {tiers.map((t, i) => (
              <div key={i} className="grid grid-cols-12 items-center gap-2">
                <RupiahInput className="col-span-4" placeholder="Min (Rp)" value={t.min_amount}
                  onChange={(e) => setTier(i, "min_amount", e.target.value)} />
                <RupiahInput className="col-span-4" placeholder="Max (kosong = \u221e)" value={t.max_amount}
                  onChange={(e) => setTier(i, "max_amount", e.target.value)} />
                <Input className="col-span-3" type="number" placeholder="Rate %" value={t.rate_pct}
                  onChange={(e) => setTier(i, "rate_pct", e.target.value)} />
                <Button size="icon" variant="ghost" className="col-span-1 h-8 w-8 text-rose-600"
                  onClick={() => rmTier(i)} disabled={tiers.length <= 1}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button size="sm" variant="outline" onClick={addTier}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Tambah Tier
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="csdefault" checked={isDefault} onCheckedChange={setIsDefault} />
            <Label htmlFor="csdefault">Jadikan skema default</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FINANCE.commissionSchemeSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan\u2026" : "Simpan Skema"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
