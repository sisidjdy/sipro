import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P51 as T } from "@/constants/testIds";

const MIN_REASON = 10;

/**
 * Dialog PENGABAIAN penahanan pencairan retensi (Fase 51A).
 *
 * Mengabaikan jaminan mutu adalah keputusan yang berdiri sendiri — karena itu ia punya
 * pintu sendiri (`POST /subcon/retentions/{id}/waive`), bukan sekadar bendera pada tombol
 * "Cairkan". Yang ditahan TIDAK hilang dari layar setelah diabaikan: ia berpindah ke daftar
 * "diabaikan" beserta siapa, kapan, dan alasannya — supaya auditor bisa bertanya kelak.
 */
export default function RetentionWaiveDialog({ row, onOpenChange, onDone }) {
  const [codes, setCodes] = useState([]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setCodes([]); setReason(""); }, [row]);

  const waivable = (row?.gate?.blocks || []).filter((b) => b.waivable);
  const notWaivable = (row?.gate?.blocks || []).filter((b) => !b.waivable);

  const toggle = (code) => setCodes((prev) => (
    prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));

  const submit = async () => {
    if (!codes.length) {
      toast.error("Pilih penahanan mana yang diabaikan — pengabaian tanpa sasaran tidak bisa diaudit.");
      return;
    }
    if (reason.trim().length < MIN_REASON) {
      toast.error(`Alasan minimal ${MIN_REASON} huruf — alasan inilah yang dibaca auditor kelak.`);
      return;
    }
    setBusy(true);
    try {
      await api.post(`/subcon/retentions/${row.id}/waive`,
        { codes, reason: reason.trim() });
      toast.success(`${codes.length} penahanan diabaikan dan tercatat atas nama Anda.`);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengabaikan penahanan.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!row} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.retentionWaiveDialog} className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-600" /> Abaikan penahanan pencairan
          </DialogTitle>
          <DialogDescription>
            {row?.retention_number} · {formatIDR(row?.amount)} untuk{" "}
            {row?.subcontractor_name}. Pengabaian tidak menghapus penahanan — ia tetap
            tercatat beserta nama Anda dan alasannya, lalu melahirkan tugas tinjauan.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Penahanan yang diabaikan</Label>
            {!waivable.length ? (
              <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                Tidak ada penahanan yang boleh diabaikan pada retensi ini.
              </p>
            ) : waivable.map((b) => (
              <label key={b.code} data-testid={T.retentionWaiveCode} data-code={b.code}
                className="flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 text-xs hover:bg-secondary/40">
                <input type="checkbox" className="mt-0.5" checked={codes.includes(b.code)}
                  onChange={() => toggle(b.code)} />
                <span>
                  <span className="font-medium">{b.label || b.code}</span>
                  <span className="mt-0.5 block text-muted-foreground">{b.detail}</span>
                </span>
              </label>
            ))}
            {notWaivable.length ? (
              <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                Tidak bisa diabaikan:{" "}
                {notWaivable.map((b) => b.label || b.code).join(", ")} — mengabaikannya berarti
                membiarkan pembukuan salah, bukan mengambil risiko bisnis.
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="waive-reason">Alasan (minimal {MIN_REASON} huruf)</Label>
            <Textarea id="waive-reason" data-testid={T.retentionWaiveReason} rows={3}
              value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="mis. adendum ADD/2026/003: klaim garansi atap ditanggung subkon lain, retensi ini bukan jaminannya" />
            <p className="text-[11px] text-muted-foreground">
              {reason.trim().length}/{MIN_REASON} huruf
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button data-testid={T.retentionWaiveCancel} variant="outline" disabled={busy}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={T.retentionWaiveSubmit} disabled={busy || !waivable.length}
            onClick={submit}>{busy ? "Menyimpan…" : "Abaikan penahanan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
