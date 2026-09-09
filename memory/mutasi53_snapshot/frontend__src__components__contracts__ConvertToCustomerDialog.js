import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { P53 } from "@/constants/testIds";

/**
 * ConvertToCustomerDialog — "Jadikan Pembeli" (Fase 53B).
 *
 * Ini pintu yang selama ini TIDAK ADA: tidak satu pun layar bisa mengubah lead yang sudah
 * booking menjadi pembeli, sehingga profil pembeli, portal pembeli, KPR, rencana bayar, dan
 * BAST hanya tersambung pada data contoh. Dialog ini memanggil `POST /deals/{id}/convert`
 * yang membuat `customers` + `contracts` sekaligus (idempoten).
 *
 * Dua hal yang sengaja diperlihatkan apa adanya:
 *   1. **Sebab belum boleh** (mis. booking belum dikonfirmasi) ditulis lengkap, bukan tombol
 *      mati tanpa penjelasan;
 *   2. **Skema pembayaran WAJIB dipilih manusia** — skema menentukan isi dokumen legal
 *      (varian SPR) dan urutan tahap legal, jadi sistem hanya MENGUSULKAN.
 */
export default function ConvertToCustomerDialog({ dealId, open, onOpenChange, onDone }) {
  const navigate = useNavigate();
  const [pre, setPre] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ scheme: "", nik: "", npwp: "", address: "", note: "" });

  const load = useCallback(async () => {
    if (!dealId) return;
    setLoading(true);
    try {
      const res = await api.get(`/deals/${dealId}/convert-preview`);
      const data = res.data.data;
      setPre(data);
      setForm((f) => ({ ...f, scheme: f.scheme || data.suggested_scheme || "" }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat pratinjau konversi.");
    } finally { setLoading(false); }
  }, [dealId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const submit = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/deals/${dealId}/convert`, {
        scheme: form.scheme || undefined,
        nik: form.nik.trim() || undefined,
        npwp: form.npwp.trim() || undefined,
        address: form.address.trim() || undefined,
        note: form.note.trim() || undefined,
      });
      const out = res.data.data;
      toast.success(out.note || "Lead menjadi pembeli.");
      onOpenChange(false);
      onDone && onDone(out);
      const cid = out?.customer?.id;
      // `?tab=` (BUKAN `?hub=`) — profil pembeli membaca penanda `tab`. Uji peramban Fase 56:
      // dengan `?hub=` pemakai mendarat di tab Ringkasan sesudah menekan "Jadikan Pembeli",
      // padahal janji dialog ini adalah membawanya ke kontrak yang baru lahir.
      if (cid) navigate(`/customers/${cid}?tab=kontrak53`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjadikan pembeli.");
    } finally { setBusy(false); }
  };

  const blocks = pre?.blocks || [];
  const blocked = blocks.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P53.convertDialog} className="max-w-lg bg-background">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="h-4 w-4" /> Jadikan Pembeli
          </DialogTitle>
          <DialogDescription>
            Lead yang sudah dikonfirmasi booking berpindah ke domain PEMBELI: kontrak,
            rencana bayar, tahap legal (PPJB → akad kredit → AJB), dan dokumennya.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <p className="text-sm text-muted-foreground">Memuat…</p>
        ) : (
          <div className="space-y-3">
            {blocked ? (
              <div data-testid={P53.convertBlocked}
                className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <p className="font-medium">Belum bisa dijadikan pembeli</p>
                <ul className="mt-1 space-y-0.5 text-xs">
                  {blocks.map((b) => <li key={b.code}>• {b.detail}</li>)}
                </ul>
              </div>
            ) : null}
            {pre?.note ? (
              <p data-testid={P53.convertNote}
                className="rounded-lg border bg-secondary/50 p-3 text-xs text-muted-foreground">
                {pre.note}
              </p>
            ) : null}
            {pre?.existing_customer ? (
              <p className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
                Sudah ada baris pembeli dengan data yang sama
                (<strong>{pre.existing_customer.name}</strong>). Data itu akan DITAUTKAN,
                bukan diduplikasi — satu orang tetap satu pembeli walau membeli unit kedua.
              </p>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <Label>Skema pembayaran (menentukan varian SPR & urutan legal)</Label>
                <Select value={form.scheme}
                  onValueChange={(v) => setForm((f) => ({ ...f, scheme: v }))}>
                  <SelectTrigger data-testid={P53.convertScheme} className="bg-background">
                    <SelectValue placeholder="Pilih skema…" />
                  </SelectTrigger>
                  <SelectContent>
                    {(pre?.schemes || []).map((s) => (
                      <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">
                  Usulan sistem: {pre?.suggested_scheme || "-"} (boleh diubah; keputusan ada
                  pada dokumen yang ditandatangani pembeli).
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-nik">NIK (opsional, dipakai untuk dedup pembeli)</Label>
                <Input id="c-nik" data-testid={P53.convertNik} className="bg-background"
                  value={form.nik} onChange={(e) => setForm((f) => ({ ...f, nik: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-npwp">NPWP (opsional)</Label>
                <Input id="c-npwp" className="bg-background" value={form.npwp}
                  onChange={(e) => setForm((f) => ({ ...f, npwp: e.target.value }))} />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="c-addr">Alamat (opsional)</Label>
                <Textarea id="c-addr" rows={2} className="bg-background" value={form.address}
                  onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} />
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Berkas yang sudah DIVERIFIKASI pada lead ini otomatis diwarisi pembeli — tidak
              diminta ulang.
            </p>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button data-testid={P53.convertSubmit} onClick={submit}
            disabled={busy || loading || blocked || !form.scheme}>
            {busy ? "Memproses…" : "Jadikan Pembeli"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
