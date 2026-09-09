import React, { useState } from "react";
import { Loader2, PartyPopper, Send } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import publicApi from "@/services/publicClient";
import { SHOWROOM } from "@/constants/testIds";

/**
 * Form minat calon pembeli di halaman publik.
 *
 * Terhubung ke ENGINE lead yang sama dengan iklan Meta/Google: nomor didedup, sales
 * ditugaskan otomatis, dan automasi WhatsApp ikut terpicu — jadi ini bukan "form
 * kirim email", tetapi lead nyata di pipeline. Field `website` adalah honeypot:
 * tersembunyi dari manusia, diisi bot, dan ditolak backend.
 */
export default function ShowroomLeadDialog({
  open, onOpenChange, token, unitCode, projectName,
}) {
  const [form, setForm] = useState({ name: "", phone: "", message: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const close = (v) => {
    onOpenChange(v);
    if (!v) { setDone(""); setError(""); setForm({ name: "", phone: "", message: "", website: "" }); }
  };

  const submit = async () => {
    if (form.name.trim().length < 2) { setError("Mohon isi nama lengkap Anda."); return; }
    if (form.phone.replace(/\D/g, "").length < 9) { setError("Nomor WhatsApp belum lengkap."); return; }
    setBusy(true); setError("");
    try {
      const res = await publicApi.post(`/public/showroom/${token}/lead`, {
        name: form.name.trim(), phone: form.phone.trim(),
        message: form.message.trim() || null, unit_code: unitCode || null,
        website: form.website || null,
      });
      setDone(res.data?.data?.message || "Terima kasih! Data Anda sudah kami terima.");
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal mengirim. Coba lagi sebentar.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent data-testid={SHOWROOM.leadDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{done ? "Permintaan terkirim" : "Saya tertarik"}</DialogTitle>
          <DialogDescription>
            {done ? "Tim marketing akan menghubungi Anda lewat WhatsApp."
              : `Tinggalkan nama & WhatsApp — tim marketing ${projectName || "kami"} akan menghubungi Anda${unitCode ? ` soal kavling ${unitCode}` : ""}.`}
          </DialogDescription>
        </DialogHeader>

        {done ? (
          <div data-testid={SHOWROOM.leadSuccess}
            className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <PartyPopper className="mt-0.5 h-5 w-5 text-emerald-600" />
            <p className="text-sm text-emerald-900">{done}</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="showroomleaddialog-nama-lengkap">Nama lengkap</Label>
              <Input id="showroomleaddialog-nama-lengkap" data-testid={SHOWROOM.leadName} value={form.name} autoComplete="name"
                placeholder="mis. Rina Puspita" onChange={(e) => set("name", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="showroomleaddialog-nomor-whatsapp">Nomor WhatsApp</Label>
              <Input id="showroomleaddialog-nomor-whatsapp" data-testid={SHOWROOM.leadPhone} value={form.phone} inputMode="tel"
                autoComplete="tel" placeholder="mis. 081234567890"
                onChange={(e) => set("phone", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="showroomleaddialog-pesan-opsional">Pesan (opsional)</Label>
              <Textarea id="showroomleaddialog-pesan-opsional" data-testid={SHOWROOM.leadMessage} rows={3} value={form.message}
                placeholder="mis. ingin survey lokasi akhir pekan"
                onChange={(e) => set("message", e.target.value)} />
            </div>
            {/* Honeypot anti-bot: disembunyikan dari pengguna & pembaca layar. */}
            <input type="text" name="website" tabIndex={-1} autoComplete="off"
              aria-hidden="true" value={form.website}
              onChange={(e) => set("website", e.target.value)}
              className="pointer-events-none absolute h-0 w-0 opacity-0" />
            {error ? (
              <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </p>
            ) : null}
            <p className="text-[11px] text-muted-foreground">
              Dengan mengirim, Anda setuju dihubungi tim marketing terkait ketersediaan unit.
            </p>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>{done ? "Tutup" : "Batal"}</Button>
          {!done ? (
            <Button data-testid={SHOWROOM.leadSubmit} onClick={submit} disabled={busy}>
              {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                : <Send className="mr-1.5 h-4 w-4" />}
              Kirim
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
