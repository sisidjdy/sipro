import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import EvidenceUploader from "@/components/patterns/EvidenceUploader";
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PETTYX } from "@/constants/testIds";

const EMPTY = { cash_account_id: "", category: "atk_kantor", description: "", amount: "", date: "", payee: "", project_id: "", file_ids: [] };

/** Catat pengeluaran langsung kas kecil: berbukti, langsung dijurnal Dr beban / Cr kas kecil. */
export default function PettyExpenseDialog({ open, policy, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [projects, setProjects] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!open) return;
    setErr("");
    setForm({ ...EMPTY, date: new Date().toISOString().slice(0, 10) });
    api.get("/projects?limit=100").then((r) => setProjects(r.data.data || [])).catch(() => setProjects([]));
  }, [open]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const amount = Number(form.amount || 0);
  const overMax = policy?.max_expense && amount > policy.max_expense;
  const needProof = policy?.require_proof && form.file_ids.length === 0;
  const valid = form.cash_account_id && form.category && form.description.trim().length >= 3 && amount > 0 && !overMax && !needProof;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      const r = await api.post("/petty-cash/expenses", {
        ...form, amount, payee: form.payee || null, project_id: form.project_id || null,
      });
      toast.success(`${r.data.data.no} dicatat → jurnal ${r.data.data.journal_no}.`);
      onSaved?.(); onClose();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(typeof d === "string" ? d : (Array.isArray(d) ? d.map((x) => x.msg).join("; ") : "Gagal mencatat pengeluaran."));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg" data-testid={PETTYX.dialog}>
        <DialogHeader>
          <DialogTitle>Pengeluaran Kas Kecil</DialogTitle>
          <DialogDescription>
            Dibayar tunai saat ini dan langsung menjadi beban — bukan kas bon.
            {policy?.max_expense ? ` Maks. ${formatIDR(policy.max_expense)} per pengeluaran.` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <CashAccountSelect label="Kas kecil" kind="cash" value={form.cash_account_id}
            onChange={(v) => set("cash_account_id", v)} testId={PETTYX.account} />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Kategori</Label>
              <ReferenceSelect group="cashbon_category" value={form.category} onChange={(v) => set("category", v)} testId={PETTYX.category} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nominal</Label>
              <RupiahInput value={form.amount} onChange={(e) => set("amount", e.target.value)} data-testid={PETTYX.amount} />
              {overMax ? <p className="text-xs text-rose-600">Melebihi batas {formatIDR(policy.max_expense)} — gunakan kas bon / tagihan AP.</p> : null}
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Keterangan</Label>
            <Input value={form.description} onChange={(e) => set("description", e.target.value)} className="h-9"
              placeholder="Mis. beli materai & fotokopi berkas SPR" data-testid={PETTYX.description} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Tanggal</Label>
              <Input type="date" value={form.date} max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => set("date", e.target.value)} className="h-9" data-testid={PETTYX.date} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Dibayar kepada (opsional)</Label>
              <Input value={form.payee} onChange={(e) => set("payee", e.target.value)} className="h-9" placeholder="Toko / penerima" data-testid={PETTYX.payee} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Proyek (opsional)</Label>
            <Select value={form.project_id || "__none__"} onValueChange={(v) => set("project_id", v === "__none__" ? "" : v)}>
              <SelectTrigger className="h-9" data-testid={PETTYX.project}><SelectValue placeholder="Tanpa proyek" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Tanpa proyek</SelectItem>
                {projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <EvidenceUploader value={form.file_ids} onChange={(v) => set("file_ids", v)} ownerType="petty_expense" max={3}
            label={policy?.require_proof ? "Bukti nota / kuitansi (wajib)" : "Bukti nota / kuitansi"} testId={PETTYX.proof}
            hint={needProof ? "Pengeluaran tidak bisa dicatat tanpa bukti." : null} />
          {err ? <p className="text-sm text-rose-600" data-testid={PETTYX.error}>{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving || !valid} data-testid={PETTYX.submit}>
            {saving ? "Menyimpan…" : "Catat & Jurnal"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
