import React, { useState } from "react";
import axios from "axios";
import { CheckCircle2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { LEGAL } from "@/constants/testIds";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const T = {
  id: { name: "Nama lengkap", contact: "Nomor WhatsApp / email terdaftar", reason: "Keterangan (opsional)",
    submit: "Kirim permintaan", sending: "Mengirim…", done: "Permintaan diterima. Nomor tiket Anda:",
    keep: "Simpan nomor ini untuk menanyakan status. Kami menanggapi paling lambat 3×24 jam kerja.",
    title: "Formulir permintaan penghapusan" },
  en: { name: "Full name", contact: "Registered WhatsApp number / email", reason: "Notes (optional)",
    submit: "Submit request", sending: "Sending…", done: "Request received. Your ticket number:",
    keep: "Keep this number to follow up. We respond within 3 working days.",
    title: "Data deletion request form" },
};

export default function DeletionRequestForm({ lang = "id" }) {
  const t = T[lang] || T.id;
  const [form, setForm] = useState({ name: "", contact: "", reason: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ticket, setTicket] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const res = await axios.post(`${API}/legal/public/deletion-requests`, { ...form, lang });
      setTicket(res.data.data.ticket);
    } catch (err) {
      setError(err?.response?.data?.detail || (lang === "en" ? "Failed to submit." : "Gagal mengirim permintaan."));
    } finally { setBusy(false); }
  };

  if (ticket) {
    return (
      <div data-testid={LEGAL.delTicket} className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-emerald-900">
        <p className="flex items-center gap-2 font-medium"><CheckCircle2 className="h-5 w-5" /> {t.done}</p>
        <p className="mt-2 font-mono text-2xl font-bold tracking-wide">{ticket}</p>
        <p className="mt-2 text-sm">{t.keep}</p>
      </div>
    );
  }
  return (
    <form data-testid={LEGAL.delForm} onSubmit={submit} className="space-y-4 rounded-xl border bg-card p-5 shadow-sm">
      <h3 className="font-heading text-base font-semibold">{t.title}</h3>
      {error ? <p data-testid={LEGAL.delError} className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p> : null}
      <input type="text" name="website" value={form.website} onChange={set("website")} className="hidden" tabIndex={-1} autoComplete="off" />
      <div className="space-y-1.5"><Label htmlFor="del-name">{t.name}</Label>
        <Input data-testid={LEGAL.delName} id="del-name" value={form.name} onChange={set("name")} required minLength={2} /></div>
      <div className="space-y-1.5"><Label htmlFor="del-contact">{t.contact}</Label>
        <Input data-testid={LEGAL.delContact} id="del-contact" value={form.contact} onChange={set("contact")} required minLength={5} placeholder="0812xxxxxxx / nama@email.com" /></div>
      <div className="space-y-1.5"><Label htmlFor="del-reason">{t.reason}</Label>
        <Textarea data-testid={LEGAL.delReason} id="del-reason" rows={3} value={form.reason} onChange={set("reason")} maxLength={1000} /></div>
      <Button data-testid={LEGAL.delSubmit} type="submit" disabled={busy}><Send className="mr-1.5 h-4 w-4" /> {busy ? t.sending : t.submit}</Button>
    </form>
  );
}
