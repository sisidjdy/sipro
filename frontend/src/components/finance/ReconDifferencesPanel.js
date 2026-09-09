import React, { useState } from "react";
import { toast } from "sonner";
import { ArrowDownToLine, BookOpen, Landmark, MessageSquareText, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { BANK } from "@/constants/testIds";
import { ReconStatusBadge } from "@/components/finance/ReconOverviewTable";

/**
 * Uraian selisih satu rekening (Fase 83): saldo rekening vs sub-akun GL pada tanggal yang sama,
 * lalu tiga keranjang — mutasi rekening tanpa pasangan di buku, jurnal buku tanpa pasangan di
 * rekening (boleh diberi alasan), dan residu yang tidak terjelaskan (dikatakan apa adanya).
 */
export default function ReconDifferencesPanel({ recon, canExplain, onChanged }) {
  const [explain, setExplain] = useState(null);
  if (!recon) return null;
  const items = recon.book_only || [];
  const bankOnly = recon.bank_only || [];

  const unexplain = async (row) => {
    try {
      await api.post("/bank/reconciliation/unexplain", { account_id: recon.account.id, journal_id: row.journal_id });
      toast.success("Alasan dihapus."); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
  };

  return (
    <div className="space-y-4" data-testid={BANK.reconDiff}>
      <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-card shadow-[var(--shadow-card)] px-4 py-3 text-sm">
        <ReconStatusBadge status={recon.status} testId={BANK.reconStatus} />
        <span>Per <b>{recon.as_of}</b> · rekening <b>{formatIDR(recon.statement_balance ?? 0)}</b> vs buku
          <b> {formatIDR(recon.book_balance)}</b> (akun {recon.gl_account_code})</span>
        {recon.statement_opening ? (
          <span className="text-muted-foreground">· saldo rekening sebelum mutasi pertama {formatIDR(recon.statement_opening)}</span>
        ) : null}
        <span className={`ml-auto font-medium ${recon.residual ? "text-rose-700" : "text-emerald-700"}`}>
          Residu tak terjelaskan: {recon.residual === null ? "belum bisa dihitung" : formatIDR(recon.residual)}
        </span>
      </div>

      {(recon.causes || []).length ? (
        <ul className="space-y-1.5">
          {recon.causes.map((c) => (
            <li key={c.code} data-testid={BANK.reconCause} data-cause={c.code}
              className={`rounded-lg border px-3 py-2 text-sm ${c.code === "unexplained"
                ? "border-rose-200 bg-rose-50 text-rose-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
              {c.detail}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border bg-card shadow-[var(--shadow-card)]" data-testid={BANK.bankOnlyList}>
          <header className="flex items-center gap-2 border-b px-4 py-2.5 text-sm font-medium">
            <Landmark className="h-4 w-4 text-sky-600" /> Di rekening, belum di buku
            <Badge variant="outline" className="ml-auto">{bankOnly.length} · {formatIDR(recon.bank_only_total)}</Badge>
          </header>
          {bankOnly.length === 0 ? (
            <p className="px-4 py-4 text-sm text-muted-foreground">Semua mutasi rekening sudah dicocokkan.</p>
          ) : (
            <ul className="divide-y text-sm">
              {bankOnly.map((t) => (
                <li key={t.id} className="flex items-center gap-3 px-4 py-2">
                  <span className="w-24 shrink-0 tabular-nums text-muted-foreground">{t.date}</span>
                  <span className="min-w-0 flex-1 truncate" title={t.description}>{t.description}<span className="ml-1 text-xs text-muted-foreground">{t.ref}</span></span>
                  <span className={`tabular-nums font-medium ${t.direction === "in" ? "text-emerald-700" : "text-rose-700"}`}>
                    {t.direction === "in" ? "+" : "−"}{formatIDR(t.amount)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="border-t px-4 py-2 text-xs text-muted-foreground">Cocokkan lewat tabel mutasi di bawah — setelah cocok, item pindah ke buku.</p>
        </section>

        <section className="rounded-lg border bg-card shadow-[var(--shadow-card)]" data-testid={BANK.bookOnlyList}>
          <header className="flex items-center gap-2 border-b px-4 py-2.5 text-sm font-medium">
            <BookOpen className="h-4 w-4 text-amber-600" /> Di buku, belum di rekening
            <Badge variant="outline" className="ml-auto">{items.length} · {formatIDR(recon.book_only_total)}</Badge>
          </header>
          {items.length === 0 ? (
            <p className="px-4 py-4 text-sm text-muted-foreground">Semua jurnal rekening ini punya pasangan mutasi.</p>
          ) : (
            <ul className="divide-y text-sm max-h-[420px] overflow-y-auto">
              {items.map((l) => (
                <li key={l.journal_id} data-testid={`${BANK.bookOnlyRow}-${l.journal_id}`}
                  className={`flex items-center gap-3 px-4 py-2 ${l.explained ? "bg-emerald-50/40" : ""}`}>
                  <span className="w-24 shrink-0 tabular-nums text-muted-foreground">{l.date}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate" title={l.memo}>{l.memo}</p>
                    <p className="truncate text-xs text-muted-foreground">{l.entry_no} · {l.counter}</p>
                    {l.explained ? (
                      <p className="text-xs text-emerald-700"><MessageSquareText className="inline h-3 w-3 mr-1" />{l.reason_label}{l.note ? ` — ${l.note}` : ""}</p>
                    ) : null}
                  </div>
                  <span className={`tabular-nums font-medium ${l.amount >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                    {l.amount >= 0 ? "+" : "−"}{formatIDR(Math.abs(l.amount))}
                  </span>
                  {canExplain ? (l.explained ? (
                    <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => unexplain(l)}
                      data-testid={`${BANK.unexplainBtn}-${l.journal_id}`} aria-label="Hapus alasan"><X className="h-3.5 w-3.5" /></Button>
                  ) : (
                    <Button size="sm" variant="outline" className="h-7" onClick={() => setExplain(l)}
                      data-testid={`${BANK.explainBtn}-${l.journal_id}`}>Beri alasan</Button>
                  )) : null}
                </li>
              ))}
            </ul>
          )}
          <p className="border-t px-4 py-2 text-xs text-muted-foreground">
            <ArrowDownToLine className="inline h-3 w-3 mr-1" />Alasan hanya dokumentasi — angka tidak berubah. Impor mutasi periode terkait agar item ini berpasangan.
          </p>
        </section>
      </div>

      <ExplainDialog row={explain} reasons={recon.reasons} accountId={recon.account.id}
        onClose={() => setExplain(null)} onSaved={onChanged} />
    </div>
  );
}

function ExplainDialog({ row, reasons, accountId, onClose, onSaved }) {
  const [reason, setReason] = useState("deposit_in_transit");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post("/bank/reconciliation/explain", { account_id: accountId, journal_id: row.journal_id, reason_code: reason, note: note || null });
      toast.success("Alasan tersimpan."); onSaved?.(); onClose(); setNote("");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan alasan."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={!!row} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid={BANK.explainDialog}>
        <DialogHeader>
          <DialogTitle>Alasan jurnal belum ada di rekening</DialogTitle>
          <DialogDescription>{row?.entry_no} · {row?.memo} · {row ? formatIDR(Math.abs(row.amount)) : ""}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Alasan</Label>
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger data-testid={BANK.explainReason} className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>{(reasons || []).map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Catatan {reason === "other" ? "(wajib)" : "(opsional)"}</Label>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} data-testid={BANK.explainNote} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={busy || (reason === "other" && !note.trim())} data-testid={BANK.explainSubmit}>Simpan</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
