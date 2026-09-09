import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Link2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import MoneyText from "@/components/patterns/MoneyText";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useReference } from "@/context/ReferenceContext";
import { formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { BANK } from "@/constants/testIds";

/**
 * BankMatchDialog — cocokkan satu mutasi rekening ke dokumen yang tepat.
 *
 * Prinsipnya: **sistem mengusulkan, manusia memutuskan**. Setiap kandidat menyebut SKOR dan
 * ALASAN kenapa ia diusulkan (nominal sama, tanggal berdekatan, nama mirip), sehingga kasir
 * tidak menekan tombol karena percaya buta. Bila tidak ada kandidat yang meyakinkan, layar
 * mengatakannya apa adanya dan mutasi tetap “belum dicocokkan” — bukan dipaksa cocok.
 */
export default function BankMatchDialog({ open, onOpenChange, txn, onDone }) {
  const { labelOf } = useReference();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState(null);
  const [manualKind, setManualKind] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!txn?.id) return;
    setLoading(true); setError(""); setPicked(null); setManualKind(""); setNote("");
    try {
      const res = await api.get(`/bank/transactions/${txn.id}/suggest`);
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat usulan pencocokan.");
    } finally { setLoading(false); }
  }, [txn?.id]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const submit = async () => {
    const kind = picked?.kind || manualKind;
    if (!kind) { toast.error("Pilih kandidat atau tentukan jenis pencocokannya."); return; }
    setBusy(true);
    try {
      const res = await api.post(`/bank/transactions/${txn.id}/match`, {
        kind, target_id: picked?.target_id || null, note: note.trim() || null,
      });
      toast.success(res.data.message || "Mutasi dicocokkan.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencocokkan mutasi.");
    } finally { setBusy(false); }
  };

  const candidates = data?.candidates || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BANK.matchDialog} className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="h-4 w-4 text-primary" /> Cocokkan mutasi rekening
          </DialogTitle>
          <DialogDescription>
            {txn ? (
              <span>
                {formatDateWIB(txn.date)} · {txn.description} ·{" "}
                <b className={txn.direction === "in" ? "text-emerald-700" : "text-rose-700"}>
                  {txn.direction === "in" ? "masuk" : "keluar"}
                </b>{" "}
                <MoneyText value={txn.amount} />
              </span>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        {loading ? <LoadingCards count={2} /> : null}
        {error ? <ErrorState message={error} onRetry={load} /> : null}

        {!loading && !error ? (
          <div className="space-y-3">
            {data?.note ? (
              <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                {data.note}
              </p>
            ) : null}

            <div className="max-h-72 space-y-2 overflow-y-auto">
              {candidates.map((c) => {
                const key = `${c.kind}:${c.target_id || "manual"}`;
                const active = picked && `${picked.kind}:${picked.target_id || "manual"}` === key;
                return (
                  <button key={key} type="button" data-testid={BANK.matchCandidate}
                    data-kind={c.kind} data-score={c.score}
                    onClick={() => { setPicked(c); setManualKind(""); }}
                    className={`w-full rounded-lg border bg-card p-3 text-left transition ${
                      active ? "border-primary ring-2 ring-primary/30" : "hover:bg-accent/40"}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium">{c.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {labelOf("bank_match_kind", c.kind)}
                          {c.sub_label ? ` · ${c.sub_label}` : ""}
                          {c.date ? ` · ${formatDateWIB(c.date)}` : ""}
                        </p>
                      </div>
                      <div className="text-right">
                        <MoneyText value={c.amount} className="text-sm font-medium" />
                        <p className="mt-0.5 inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium">
                          <Sparkles className="h-3 w-3" /> skor {c.score}
                        </p>
                      </div>
                    </div>
                    {(c.reasons || []).length ? (
                      <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
                        {c.reasons.map((r, i) => <li key={i}>• {r}</li>)}
                      </ul>
                    ) : null}
                  </button>
                );
              })}
              {!candidates.length ? (
                <p className="rounded-lg border border-dashed bg-card p-4 text-sm text-muted-foreground">
                  Belum ada kandidat. Pilih jenis pencocokan manual di bawah bila mutasi ini
                  memang bukan pembayaran pembeli.
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <Label>Atau tentukan jenis pencocokan sendiri</Label>
              <ReferenceSelect group="bank_match_kind" value={manualKind}
                testId={BANK.matchKindSelect} allowEmpty emptyLabel="— pakai kandidat di atas —"
                onChange={(v) => { setManualKind(v); setPicked(null); }} />
              <p className="text-xs text-muted-foreground">
                Jenis yang butuh dokumen (termin pembeli, tagihan vendor, rekap upah) hanya
                bisa dipilih lewat kandidat, karena harus menunjuk dokumen tertentu.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="bank-match-note">Catatan (opsional)</Label>
              <Textarea id="bank-match-note" rows={2} value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Mis. konfirmasi WA dari pembeli tanggal 16." />
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={BANK.matchSubmit} disabled={busy || loading} onClick={submit}>
            {busy ? "Memproses…" : "Cocokkan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
