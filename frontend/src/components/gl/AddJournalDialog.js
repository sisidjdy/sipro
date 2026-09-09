import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, AlertTriangle, Lock } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

const NEW_LINE = () => ({ account_code: "", debit: "", credit: "" });

export default function AddJournalDialog({ open, onOpenChange, onDone }) {
  const [memo, setMemo] = useState("");
  const [date, setDate] = useState("");
  const [lines, setLines] = useState([NEW_LINE(), NEW_LINE()]);
  const [accounts, setAccounts] = useState([]);
  const [closed, setClosed] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMemo(""); setDate(""); setLines([NEW_LINE(), NEW_LINE()]); setErr("");
    api.get("/gl/accounts").then((r) => setAccounts(r.data.data || [])).catch(() => setAccounts([]));
    api.get("/gl/periods")
      .then((r) => setClosed((r.data.data || []).filter((p) => p.status === "closed").map((p) => p.period)))
      .catch(() => setClosed([]));
  }, [open]);

  const setLine = (i, k, v) => setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, [k]: v } : l)));
  const totals = useMemo(() => {
    const td = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
    const tc = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
    return { td, tc, balanced: td === tc && td > 0 };
  }, [lines]);

  // Periode tertutup: cegah lebih awal (jelas di UI) — backend juga menolak (400).
  const periodClosed = date ? closed.includes(date.slice(0, 7)) : false;

  const submit = async () => {
    setErr("");
    if (!memo.trim()) { setErr("Isi keterangan jurnal."); toast.error("Isi keterangan jurnal."); return; }
    if (!totals.balanced) { setErr("Jurnal harus seimbang (total debit = kredit) dan > 0."); return; }
    const payloadLines = lines.filter((l) => l.account_code && ((Number(l.debit) || 0) > 0 || (Number(l.credit) || 0) > 0))
      .map((l) => ({ account_code: l.account_code, debit: Math.round(Number(l.debit) || 0), credit: Math.round(Number(l.credit) || 0) }));
    if (payloadLines.length < 2) { setErr("Minimal 2 baris akun bernilai."); return; }
    setBusy(true);
    try {
      await api.post("/gl/journals", { memo, date: date ? new Date(date).toISOString() : null, lines: payloadLines });
      toast.success("Jurnal manual diposting.");
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      const msg = e?.response?.data?.detail || "Gagal memposting jurnal.";
      setErr(msg);
      toast.error(msg);
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Jurnal Manual (Penyesuaian)</DialogTitle>
          <DialogDescription>Entri double-entry — total debit harus sama dengan total kredit.</DialogDescription>
        </DialogHeader>

        {periodClosed ? (
          <div data-testid="journal-period-closed"
            className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <Lock className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Periode <b>{date.slice(0, 7)}</b> sudah ditutup — jurnal manual tidak dapat dibukukan di
              periode tertutup. Gunakan tanggal di periode terbuka, atau minta owner membuka kembali
              periode tersebut di Laporan Keuangan → Tutup Periode.
            </span>
          </div>
        ) : null}
        {err ? (
          <div data-testid="journal-error"
            className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> <span>{err}</span>
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="jv-memo">Keterangan</Label>
            <Input id="jv-memo" data-testid={GL.journalMemo} value={memo}
              onChange={(e) => setMemo(e.target.value)} placeholder="mis. Beban sewa kantor" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="jv-date">Tanggal</Label>
            <Input id="jv-date" data-testid={GL.journalDate} type="date" value={date}
              onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
        <div className="mt-2 space-y-2">
          <div className="flex items-center justify-between">
            <Label>Baris Akun</Label>
            <Button data-testid={GL.journalLineAdd} type="button" variant="outline" size="sm" onClick={() => setLines((l) => [...l, NEW_LINE()])}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Baris
            </Button>
          </div>
          {lines.map((l, i) => (
            <div key={i} data-testid={GL.journalLineRow} data-line-index={i}
              className="grid grid-cols-12 items-end gap-2 rounded-lg border bg-secondary/40 p-2">
              <div className="col-span-12 sm:col-span-5">
                <Select value={l.account_code} onValueChange={(v) => setLine(i, "account_code", v)}>
                  <SelectTrigger data-testid={GL.journalLineAccount} data-line-index={i}
                    aria-label={`Akun baris ${i + 1}`} className="h-9">
                    <SelectValue placeholder="Pilih akun…" />
                  </SelectTrigger>
                  <SelectContent>{accounts.map((a) => <SelectItem key={a.code} value={a.code}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="col-span-5 sm:col-span-3">
                <RupiahInput data-testid={GL.journalLineDebit} data-line-index={i}
                  aria-label={`Debit baris ${i + 1}`} className="h-9" value={l.debit}
                  onChange={(e) => setLine(i, "debit", e.target.value)} placeholder="Debit" />
              </div>
              <div className="col-span-5 sm:col-span-3">
                <RupiahInput data-testid={GL.journalLineCredit} data-line-index={i}
                  aria-label={`Kredit baris ${i + 1}`} className="h-9" value={l.credit}
                  onChange={(e) => setLine(i, "credit", e.target.value)} placeholder="Kredit" />
              </div>
              <div className="col-span-2 sm:col-span-1">
                {lines.length > 2 ? (
                  <Button type="button" variant="ghost" size="icon" data-line-index={i}
                    aria-label={`Hapus baris ${i + 1}`} className="h-9 w-9 text-rose-600"
                    onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <div className={`flex items-center justify-between rounded-lg p-3 text-sm ${totals.balanced ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>
          <span>Debit: <b className="tabular-nums">{formatIDR(totals.td)}</b> · Kredit: <b className="tabular-nums">{formatIDR(totals.tc)}</b></span>
          <span className="font-semibold">{totals.balanced ? "Seimbang" : "Belum seimbang"}</span>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={GL.journalAddSubmit} onClick={submit}
            disabled={busy || !totals.balanced || periodClosed}>
            {busy ? "Memposting…" : "Posting Jurnal"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
