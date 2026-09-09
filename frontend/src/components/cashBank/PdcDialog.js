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
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PDC } from "@/constants/testIds";

const EMPTY = { kind: "bg", bank_name: "", instrument_no: "", issuer_name: "", amount: "", due_date: "", received_date: "", deal_id: "", note: "" };

/** Catat penerimaan cek/giro mundur: jurnal memorandum Dr 1-1350 / Cr 2-1480; AR belum berkurang. */
export default function PdcDialog({ open, kinds, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [q, setQ] = useState("");
  const [deals, setDeals] = useState([]);
  const [picked, setPicked] = useState(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!open) return;
    setForm({ ...EMPTY, received_date: new Date().toISOString().slice(0, 10) });
    setQ(""); setDeals([]); setPicked(null); setErr("");
  }, [open]);

  useEffect(() => {
    if (!open || q.trim().length < 2) { setDeals([]); return; }
    const t = setTimeout(() => {
      api.get("/finance/ar", { params: { q: q.trim(), limit: 8, status: "unpaid,partial" } })
        .then((r) => setDeals(r.data.data || [])).catch(() => setDeals([]));
    }, 300);
    return () => clearTimeout(t);
  }, [q, open]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const valid = form.bank_name.trim().length >= 2 && form.instrument_no.trim().length >= 2 && Number(form.amount) > 0 && form.due_date.length === 10;

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      const r = await api.post("/pdc", { ...form, amount: Number(form.amount), deal_id: form.deal_id || null,
        issuer_name: form.issuer_name || null, note: form.note || null, received_date: form.received_date || null });
      toast.success(`${r.data.data.no} dicatat sebagai giro belum cair → jurnal ${r.data.data.journal_no}.`);
      onSaved?.(); onClose();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(typeof d === "string" ? d : (Array.isArray(d) ? d.map((x) => x.msg).join("; ") : "Gagal mencatat giro."));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg" data-testid={PDC.dialog}>
        <DialogHeader>
          <DialogTitle>Terima Cek / Giro Mundur</DialogTitle>
          <DialogDescription>Dicatat sebagai <b>Giro Belum Cair</b>. Piutang baru berkurang & kwitansi terbit saat bank mengkliringnya.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Jenis warkat</Label>
              <Select value={form.kind} onValueChange={(v) => set("kind", v)}>
                <SelectTrigger className="h-9" data-testid={PDC.kind}><SelectValue /></SelectTrigger>
                <SelectContent>{(kinds || []).map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Bank penerbit</Label>
              <ReferenceSelect group="financing_bank" value={form.bank_name} onChange={(v) => set("bank_name", v)} testId={PDC.bank} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nomor warkat</Label>
              <Input value={form.instrument_no} onChange={(e) => set("instrument_no", e.target.value)} className="h-9" placeholder="BG 123456" data-testid={PDC.instrumentNo} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Nominal</Label>
              <RupiahInput value={form.amount} onChange={(e) => set("amount", e.target.value)} data-testid={PDC.amount} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Jatuh tempo giro</Label>
              <Input type="date" value={form.due_date} onChange={(e) => set("due_date", e.target.value)} className="h-9" data-testid={PDC.dueDate} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Tanggal terima</Label>
              <Input type="date" value={form.received_date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => set("received_date", e.target.value)} className="h-9" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Tagihan pembeli (cari unit / nama) — opsional</Label>
            {picked ? (
              <div className="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2 text-sm">
                <span>{picked.unit_code} · {picked.lead_name} <span className="text-muted-foreground">sisa {formatIDR(picked.outstanding)}</span></span>
                <Button size="sm" variant="ghost" className="h-7" onClick={() => { setPicked(null); set("deal_id", ""); }}>Ganti</Button>
              </div>
            ) : (
              <>
                <Input value={q} onChange={(e) => setQ(e.target.value)} className="h-9" placeholder="Ketik kode unit atau nama pembeli" data-testid={PDC.dealSearch} />
                {deals.length ? (
                  <div className="rounded-md border divide-y max-h-40 overflow-auto">
                    {deals.map((d) => (
                      <button key={d.deal_id} type="button" className="w-full text-left px-3 py-2 text-sm hover:bg-muted"
                        data-testid={`${PDC.dealOption}-${d.deal_id}`}
                        onClick={() => { setPicked(d); set("deal_id", d.deal_id); if (!form.issuer_name) set("issuer_name", d.lead_name || ""); }}>
                        <span className="font-medium">{d.unit_code}</span> · {d.lead_name} <span className="text-muted-foreground">sisa {formatIDR(d.outstanding)}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </>
            )}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Penerbit / dari</Label>
              <Input value={form.issuer_name} onChange={(e) => set("issuer_name", e.target.value)} className="h-9" placeholder="Nama pembeli / pihak" data-testid={PDC.issuer} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Catatan</Label>
              <Input value={form.note} onChange={(e) => set("note", e.target.value)} className="h-9" placeholder="Opsional" />
            </div>
          </div>
          {err ? <p className="text-sm text-rose-600" data-testid={PDC.error}>{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving || !valid} data-testid={PDC.submit}>{saving ? "Menyimpan…" : "Catat giro"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
