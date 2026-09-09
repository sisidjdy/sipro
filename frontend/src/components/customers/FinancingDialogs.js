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
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { CUSTOMERS } from "@/constants/testIds";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import ReferenceItems from "@/components/patterns/ReferenceItems";

// --- Add KPR / Financing application ---
export function AddFinancingDialog({ open, onOpenChange, customer, onDone }) {
  const [deals, setDeals] = useState([]);
  const [form, setForm] = useState({ deal_id: "", bank_name: "", plafon: "", dp_amount: "", tenor_months: "180", interest_rate_pct: "" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!open) return;
    setForm({ deal_id: "", bank_name: "", plafon: "", dp_amount: "", tenor_months: "180", interest_rate_pct: "" });
    (async () => {
      try {
        const res = await api.get("/deals");
        const all = res.data?.data || [];
        const mine = customer?.lead_id ? all.filter((d) => d.lead_id === customer.lead_id) : [];
        setDeals(mine.length ? mine : all);
      } catch { setDeals([]); }
    })();
  }, [open, customer]);

  const submit = async () => {
    if (!form.deal_id) { toast.error("Pilih deal/unit terlebih dahulu."); return; }
    if (!form.bank_name || !form.plafon) { toast.error("Bank & plafon wajib diisi."); return; }
    setBusy(true);
    try {
      const res = await api.post("/financing", {
        deal_id: form.deal_id, customer_id: customer?.id,
        bank_name: form.bank_name, plafon: Number(form.plafon),
        dp_amount: Number(form.dp_amount || 0), tenor_months: Number(form.tenor_months || 0),
        interest_rate_pct: Number(form.interest_rate_pct || 0),
      });
      // Fase 30a: hasil pra-skrining SLIK lead ikut menempel; bila tidak lolos, petugas
      // langsung diberi tahu (bukan menemukannya nanti saat bank menolak).
      const warn = res.data?.prescreen_warning;
      const pre = res.data?.prescreen;
      if (warn) toast.warning(warn);
      else if (pre) toast.success(`Pengajuan KPR dibuat · pra-skrining lead: ${pre.label}.`);
      else toast.success("Pengajuan KPR dibuat.");
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat pengajuan KPR.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ajukan KPR</DialogTitle>
          <DialogDescription>Pengajuan pembiayaan terkait deal/unit pembeli.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Deal / Unit</Label>
            <Select value={form.deal_id} onValueChange={(v) => set("deal_id", v)}>
              <SelectTrigger data-testid="financing-deal-select"><SelectValue placeholder="Pilih deal" /></SelectTrigger>
              <SelectContent>
                {deals.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {(d.lead_name || "Deal")} · {formatIDR(d.price)} · {String(d.id).slice(0, 6)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5"><Label htmlFor="bk">Bank</Label>
            <ReferenceSelect group="financing_bank" value={form.bank_name}
              onChange={(v) => set("bank_name", v)} testId="financing-bank-select"
              placeholder="Pilih bank…" /></div>
          <div className="space-y-1.5"><Label htmlFor="pl">Plafon (Rp)</Label>
            <RupiahInput id="pl" value={form.plafon} onChange={(e) => set("plafon", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="dp">DP (Rp)</Label>
            <RupiahInput id="dp" value={form.dp_amount} onChange={(e) => set("dp_amount", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="tn">Tenor (bulan)</Label>
            <Input id="tn" type="number" value={form.tenor_months} onChange={(e) => set("tenor_months", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="ir">Bunga (%/th)</Label>
            <Input id="ir" type="number" value={form.interest_rate_pct} onChange={(e) => set("interest_rate_pct", e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={CUSTOMERS.financingAddSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Ajukan KPR"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- SLIK / BI check result ---
export function SlikDialog({ open, onOpenChange, financing, onDone }) {
  const [status, setStatus] = useState("clear");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  // Fase 30a: hasil PRA-SKRINING lead ikut menempel pada pengajuan. Dipakai sebagai
  // nilai awal form supaya petugas tidak mengetik ulang — tetapi hasil RESMI bank tetap
  // harus dikonfirmasi manusia (pra-skrining tidak pernah otomatis jadi hasil resmi).
  const pre = financing?.slik_prescreen || null;
  useEffect(() => {
    if (!open) return;
    setStatus(pre?.status && pre.status !== "pending" ? pre.status : "clear");
    setNote(pre ? `Mengacu pra-skrining lead (${pre.label || pre.status})${pre.note ? `: ${pre.note}` : ""}` : "");
  }, [open, financing]);   // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    if (!financing?.id) return;
    setBusy(true);
    try {
      await api.post(`/financing/${financing.id}/slik`, { slik_status: status, note: note || null });
      toast.success(`Hasil SLIK: ${status}.`);
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memperbarui SLIK.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Hasil BI / SLIK Check</DialogTitle>
          <DialogDescription>{financing ? `${financing.bank_name} · ${formatIDR(financing.plafon)}` : ""}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {pre ? (
            <div data-testid="financing-slik-prescreen"
              className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-900">
              <p className="font-semibold">
                Pra-skrining lead: {pre.label || pre.status} (SIMULASI)
              </p>
              <p>
                {(pre.evidence || []).length
                  ? `${pre.evidence.length} bukti iDeb dilampirkan`
                  : "tanpa lampiran"} · diperiksa {pre.checked_by || "-"}
                {pre.checked_at ? ` · ${String(pre.checked_at).slice(0, 10)}` : ""}
              </p>
              <p className="mt-1">
                Ini BUKAN hasil resmi bank — konfirmasi hasil resmi di bawah agar status KPR
                berubah.
              </p>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label>Status</Label>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger data-testid="financing-slik-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <ReferenceItems group="slik_status" />
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5"><Label htmlFor="sn">Catatan</Label>
            <Textarea id="sn" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={CUSTOMERS.slikSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan Hasil SLIK"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Staged disbursement ---
export function DisburseDialog({ open, onOpenChange, financing, onDone }) {
  const [form, setForm] = useState({ amount: "", milestone: "", min_progress: "0", note: "" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  useEffect(() => {
    if (open) { setForm({ amount: "", milestone: "", min_progress: "0", note: "" }); }
  }, [open]);

  const remaining = (financing?.plafon || 0) - (financing?.disbursed_total || 0);

  const submit = async () => {
    if (!financing?.id) return;
    if (!form.amount || Number(form.amount) <= 0) { toast.error("Nominal pencairan harus > 0."); return; }
    if (!form.milestone) { toast.error("Milestone wajib diisi."); return; }
    setBusy(true);
    try {
      const res = await api.post(`/financing/${financing.id}/disburse`, {
        amount: Number(form.amount), milestone: form.milestone,
        min_progress: Number(form.min_progress || 0), note: form.note || null,
      });
      const bk = res.data?.ar_booking || {};
      toast.success(bk.booked
        ? `Pencairan tercatat & dibukukan: piutang berkurang ${formatIDR(bk.applied || 0)}`
          + (bk.deposit_amount ? `, ${formatIDR(bk.deposit_amount)} jadi titipan.` : ".")
        : `Pencairan tercatat (belum dibukukan ke AR${bk.reason ? `: ${bk.reason}` : ""}).`);
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencatat pencairan.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Pencairan KPR (Bertahap)</DialogTitle>
          <DialogDescription>
            {financing ? `Sisa plafon ${formatIDR(remaining)} · terkait milestone konstruksi` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="am">Nominal (Rp)</Label>
            <RupiahInput id="am" value={form.amount} onChange={(e) => set("amount", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="mp">Min. Progres (%)</Label>
            <Input id="mp" type="number" value={form.min_progress} onChange={(e) => set("min_progress", e.target.value)} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="ms">Milestone</Label>
            <Input id="ms" value={form.milestone} onChange={(e) => set("milestone", e.target.value)} placeholder="mis. Pencairan Termin I (Pondasi)" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="dn">Catatan</Label>
            <Textarea id="dn" rows={2} value={form.note} onChange={(e) => set("note", e.target.value)} /></div>
          <div data-testid="financing-book-to-ar-note" className="rounded-lg border bg-secondary p-3 text-[12px] sm:col-span-2">
            <span className="font-medium">Otomatis dibukukan sebagai penerimaan AR.</span> Dana yang cair dari bank
            adalah kas masuk: piutang pembeli berkurang dan jurnal kas terbentuk (Dr Bank / Cr Uang Muka).
            Kelebihan di atas sisa tagihan menjadi titipan pelanggan. Pencairan ditolak bila jadwal tagihan unit belum terbit.
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={CUSTOMERS.disburseSubmit} onClick={submit} disabled={busy}>
            {busy ? "Memproses…" : "Catat Pencairan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
