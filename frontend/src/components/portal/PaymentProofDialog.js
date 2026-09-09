import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { formatIDR } from "@/utils/formatters";
import portalApi from "@/services/portalClient";
import { INTAKE } from "@/constants/testIds";

const today = () => new Date().toISOString().slice(0, 10);

/**
 * PaymentProofDialog (Portal Pelanggan, Fase 47B) — pembeli mengirim bukti transfer.
 *
 * Yang PENTING dan ditulis terang-terangan di layar: ini KLAIM, bukan pelunasan. Tagihan
 * baru berubah setelah finance memverifikasi. Sebelum fase ini pembeli tidak punya jalan
 * resmi menyetorkan bukti sehingga bukti berkeliaran di WhatsApp dan status pembayaran
 * menjadi tafsir masing-masing pihak.
 */
export default function PaymentProofDialog({ open, onOpenChange, deal, onDone, endpoint = "/portal/payments/proof", title = "Kirim bukti transfer" }) {
  const fileRef = useRef(null);
  const [form, setForm] = useState({ amount: "", transfer_date: today(), bank_name: "",
    note: "" });
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setForm({ amount: "", transfer_date: today(), bank_name: "", note: "" });
    setFiles([]); setError("");
    if (fileRef.current) fileRef.current.value = "";
  }, [open]);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !deal?.deal_id) return;
    setUploading(true); setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("deal_id", deal.deal_id);
      const res = await portalApi.post("/portal/payments/proof/upload", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      setFiles((prev) => [...prev, res.data.data]);
      toast.success("Berkas bukti terunggah.");
    } catch (err) {
      setError(err?.response?.data?.detail || "Gagal mengunggah berkas bukti.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const submit = async () => {
    if (!files.length) { setError("Lampirkan foto/PDF bukti transfer lebih dulu."); return; }
    if (!Number(form.amount)) { setError("Isi nominal transfer sesuai bukti."); return; }
    setBusy(true); setError("");
    try {
      const res = await portalApi.post(endpoint, {
        deal_id: deal.deal_id, amount: Number(form.amount),
        transfer_date: form.transfer_date, bank_name: form.bank_name.trim() || null,
        note: form.note.trim() || null, file_ids: files.map((f) => f.id),
      });
      toast.success(res.data.message || "Bukti transfer terkirim.");
      onOpenChange(false);
      onDone?.();
    } catch (err) {
      setError(err?.response?.data?.detail || "Gagal mengirim bukti transfer.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={INTAKE.portalDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Unit {deal?.unit_code || "-"}
            {deal?.summary?.outstanding
              ? ` · sisa tagihan ${formatIDR(deal.summary.outstanding)}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="proof-amount">Nominal transfer (Rp)</Label>
            <RupiahInput id="proof-amount" data-testid={INTAKE.portalAmount}
              value={form.amount} placeholder="Contoh: 25000000"
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="proof-date">Tanggal transfer</Label>
              <Input id="proof-date" type="date" data-testid={INTAKE.portalDate} max={today()}
                value={form.transfer_date}
                onChange={(e) => setForm((f) => ({ ...f, transfer_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="proof-bank">Nama bank pengirim</Label>
              <Input id="proof-bank" value={form.bank_name} placeholder="BCA / Mandiri / …"
                onChange={(e) => setForm((f) => ({ ...f, bank_name: e.target.value }))} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="proof-file">Foto / PDF bukti transfer</Label>
            <Input id="proof-file" ref={fileRef} type="file" data-testid={INTAKE.portalFile}
              accept="image/*,application/pdf" disabled={uploading} onChange={upload} />
            <p className="text-xs text-slate-500">
              Maksimal 8 MB per berkas. Bisa mengirim lebih dari satu (pilih berulang).
            </p>
            {files.length ? (
              <ul className="space-y-1 text-xs text-slate-600">
                {files.map((f) => <li key={f.id}>✓ {f.filename}</li>)}
              </ul>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="proof-note">Catatan (opsional)</Label>
            <Textarea id="proof-note" rows={2} value={form.note}
              placeholder="Mis. transfer dari rekening pribadi atas nama suami saya."
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
          </div>

          <p className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5" />
            Bukti ini akan diperiksa bagian keuangan. Sisa tagihan Anda BELUM berkurang
            sampai bukti diverifikasi — statusnya bisa Anda pantau di halaman ini.
          </p>

          {error ? (
            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={INTAKE.portalSubmit} disabled={busy || uploading}
            onClick={submit}>
            <Upload className="mr-1.5 h-4 w-4" />
            {busy ? "Mengirim…" : "Kirim bukti"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
