import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { FileSignature, ScrollText, CheckCircle2, Landmark, Circle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import StatusPill from "@/components/patterns/StatusPill";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { DEALS as T } from "@/constants/testIds";

const STEPS = [
  { key: "reserved", label: "Reservasi" },
  { key: "booked", label: "Booking" },
  { key: "ppjb", label: "PPJB" },
  { key: "ajb", label: "AJB / Lunas" },
];

function stepIndex(legal) {
  const { status, legal_stage } = legal || {};
  if (legal_stage === "ajb" || status === "completed") return 3;
  if (legal_stage === "ppjb") return 2;
  if (status === "booked") return 1;
  return 0;
}

export default function DealLegalDialog({ deal, open, onOpenChange, onChanged }) {
  const [legal, setLegal] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ open: false, kind: null, number: "", notary: "", note: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!deal?.id || !open) return;
    setLoading(true);
    try {
      const res = await api.get(`/deals/${deal.id}/legal`);
      setLegal(res.data.data);
    } catch (e) { toast.error("Gagal memuat status legal."); }
    finally { setLoading(false); }
  }, [deal, open]);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    setBusy(true);
    try {
      if (form.kind === "ppjb") {
        await api.post(`/deals/${deal.id}/ppjb`, { number: form.number || null, note: form.note || null });
        toast.success("PPJB ditandatangani.");
      } else {
        await api.post(`/deals/${deal.id}/ajb`, {
          number: form.number || null, notary: form.notary || null, note: form.note || null });
        toast.success("AJB ditandatangani — unit SOLD.");
      }
      setForm({ open: false, kind: null, number: "", notary: "", note: "" });
      await load();
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
    finally { setBusy(false); }
  };

  const idx = stepIndex(legal);
  const pay = legal?.payment || {};

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent data-testid={T.legalDialog} className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ScrollText className="h-5 w-5 text-primary" /> Legal & Serah Terima
            </DialogTitle>
            <DialogDescription>
              {legal?.unit_code} · {legal?.lead_name}
            </DialogDescription>
          </DialogHeader>

          {loading ? <p className="text-sm text-muted-foreground">Memuat...</p> : (
            <div className="space-y-4">
              {/* Stepper */}
              <div className="flex items-center justify-between">
                {STEPS.map((s, i) => (
                  <React.Fragment key={s.key}>
                    <div className="flex flex-col items-center gap-1">
                      {i <= idx ? (
                        <CheckCircle2 className={`h-6 w-6 ${i === idx ? "text-primary" : "text-emerald-500"}`} />
                      ) : <Circle className="h-6 w-6 text-muted-foreground/40" />}
                      <span className={`text-[11px] ${i <= idx ? "font-medium" : "text-muted-foreground"}`}>{s.label}</span>
                    </div>
                    {i < STEPS.length - 1 ? (
                      <div className={`mx-1 h-0.5 flex-1 ${i < idx ? "bg-emerald-400" : "bg-muted"}`} />
                    ) : null}
                  </React.Fragment>
                ))}
              </div>

              {/* Payment */}
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Pembayaran</span>
                  <span className="tabular-nums font-medium">{formatIDR(pay.paid)} / {formatIDR(pay.total)}</span>
                </div>
                <Progress value={pay.paid_pct || 0} className="h-2" />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Terbayar {pay.paid_pct || 0}% · Sisa {formatIDR(pay.outstanding)}
                </p>
              </div>

              {/* Financing */}
              {legal?.financing ? (
                <div className="flex items-center gap-2 rounded-xl border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
                  <Landmark className="h-4 w-4 text-primary" />
                  <span>KPR {legal.financing.bank} · plafon {formatIDR(legal.financing.plafon)}</span>
                  <span className="ml-auto"><StatusPill status={legal.financing.status} group="financing_status" /></span>
                </div>
              ) : null}

              {/* PPJB / AJB records */}
              {legal?.ppjb ? (
                <div className="rounded-lg border bg-card p-2.5 text-sm shadow-[var(--shadow-card)]">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">PPJB {legal.ppjb.number}</span>
                    <span className="text-xs text-muted-foreground">{formatDateWIB(legal.ppjb.signed_date)}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">DP saat PPJB: {legal.ppjb.dp_pct}%</p>
                </div>
              ) : null}
              {legal?.ajb ? (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-emerald-800">AJB {legal.ajb.number}</span>
                    <span className="text-xs text-emerald-700">{formatDateWIB(legal.ajb.signed_date)}</span>
                  </div>
                  {legal.ajb.notary ? <p className="text-[11px] text-emerald-700">Notaris: {legal.ajb.notary}</p> : null}
                </div>
              ) : null}

              {/* Actions */}
              <div className="flex flex-wrap gap-2">
                {legal?.status === "booked" && !legal?.ppjb ? (
                  <Button data-testid={T.ppjbSignBtn} size="sm"
                    onClick={() => setForm({ open: true, kind: "ppjb", number: "", notary: "", note: "" })}>
                    <FileSignature className="mr-1.5 h-4 w-4" /> Tandatangani PPJB
                  </Button>
                ) : null}
                {legal?.legal_stage === "ppjb" ? (
                  <Button data-testid={T.ajbSignBtn} size="sm"
                    onClick={() => setForm({ open: true, kind: "ajb", number: "", notary: "", note: "" })}>
                    <FileSignature className="mr-1.5 h-4 w-4" /> Tandatangani AJB
                  </Button>
                ) : null}
                {legal?.legal_stage === "ajb" ? (
                  <span className="flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700">
                    <CheckCircle2 className="h-4 w-4" /> Unit terjual (SOLD)
                  </span>
                ) : null}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Sign form */}
      <Dialog open={form.open} onOpenChange={(v) => !v && setForm((f) => ({ ...f, open: false }))}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{form.kind === "ppjb" ? "Tandatangani PPJB" : "Tandatangani AJB"}</DialogTitle>
            <DialogDescription>
              {form.kind === "ppjb"
                ? "Perjanjian Pengikatan Jual Beli. Kosongkan nomor untuk otomatis."
                : "Akta Jual Beli (notaris). Menyelesaikan deal & menandai unit SOLD."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Nomor {form.kind === "ppjb" ? "PPJB" : "AJB"} (opsional)</Label>
              <Input data-testid={T.legalNumberInput} value={form.number}
                onChange={(e) => setForm((f) => ({ ...f, number: e.target.value }))}
                placeholder="otomatis bila kosong" />
            </div>
            {form.kind === "ajb" ? (
              <div className="space-y-1.5">
                <Label htmlFor="deallegaldialog-notaris-ppat">Notaris/PPAT</Label>
                <Input id="deallegaldialog-notaris-ppat" data-testid={T.legalNotaryInput} value={form.notary}
                  onChange={(e) => setForm((f) => ({ ...f, notary: e.target.value }))}
                  placeholder="mis. Notaris Budi, S.H." />
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="deallegaldialog-catatan">Catatan</Label>
              <Textarea id="deallegaldialog-catatan" value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setForm((f) => ({ ...f, open: false }))} disabled={busy}>Batal</Button>
            <Button data-testid={T.legalSubmit} onClick={submit} disabled={busy}>
              {busy ? "Menyimpan..." : "Tandatangani"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
