import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Trash2 } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import api from "@/services/apiClient";

/**
 * DeleteEntityButton — tombol "Hapus" untuk data master (lead, customer, unit, proyek) dan transaksi (deal).
 * Sebelum konfirmasi, memanggil `checkUrl` (…/delete-check) agar pemakai melihat ALASAN bila
 * data tidak bisa dihapus (jejak transaksi), bukan sekadar tombol gagal.
 *
 * HAPUS PAKSA: bila backend menjawab `can_force` (Direksi/Super Admin), data yang punya jejak
 * transaksi tetap bisa dihapus BESERTA seluruh transaksinya — wajib alasan ≥10 huruf, terekam di audit.
 */
export default function DeleteEntityButton({ label = "Hapus", entity, name, checkUrl, deleteUrl,
  onDeleted, testId = "entity-delete", size = "sm", variant = "outline", className = "",
  forceOnly = false }) {
  const [open, setOpen] = useState(false);
  const [check, setCheck] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!open) return;
    setCheck(null); setReason("");
    api.get(checkUrl).then((r) => setCheck(r.data.data))
      .catch((e) => setCheck({ can_delete: false, error: e?.response?.data?.detail || "Gagal memeriksa data." }));
  }, [open, checkUrl]);

  const blockers = Object.entries(check?.blockers || {});
  const needForce = forceOnly || (check && !check.can_delete && blockers.length > 0);
  const canForce = !!check?.can_force;
  const reasonOk = reason.trim().length >= 10;
  const canSubmit = check && (needForce ? (canForce && reasonOk) : check.can_delete);

  const run = async () => {
    setBusy(true);
    try {
      const r = await api.delete(deleteUrl, { params: needForce ? { force: true, reason: reason.trim() } : undefined });
      toast.success(`${entity} ${name || ""} dihapus${needForce ? " beserta transaksinya" : ""}.`.replace(/\s+/g, " "));
      setOpen(false);
      onDeleted?.(r.data?.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || `Gagal menghapus ${entity.toLowerCase()}.`);
    } finally { setBusy(false); }
  };

  return (
    <>
      <Button data-testid={`${testId}-btn`} size={size} variant={variant}
        className={`text-rose-700 hover:text-rose-800 ${className}`} onClick={() => setOpen(true)}>
        <Trash2 className="mr-1.5 h-4 w-4" /> {label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid={`${testId}-dialog`} className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-rose-600" /> Hapus {entity.toLowerCase()} {name || ""}?
            </DialogTitle>
            <DialogDescription>
              Data yang dihapus tidak bisa dikembalikan. Catatan turunan (aktivitas, tugas, jadwal tanpa
              bukti kerja) ikut dibersihkan.
            </DialogDescription>
          </DialogHeader>
          {!check ? <p className="text-xs text-muted-foreground">Memeriksa jejak transaksi…</p> : null}
          {check && needForce ? (
            <div data-testid={`${testId}-blocked`} className={`rounded-md border p-3 text-xs ${canForce ? "border-amber-200 bg-amber-50 text-amber-900" : "border-rose-200 bg-rose-50 text-rose-900"}`}>
              <p className="font-semibold">
                {check.error ? `Tidak bisa dihapus: ${check.error}` : (canForce ? "Punya jejak transaksi yang akan IKUT TERHAPUS:" : "Tidak bisa dihapus — masih dipakai oleh:")}
              </p>
              {blockers.length ? (
                <ul className="mt-1 list-disc pl-4">
                  {blockers.map(([k, v]) => <li key={k} data-testid={`${testId}-blocker`}>{v} {k}</li>)}
                </ul>
              ) : null}
              {check.note ? <p className="mt-1">{check.note}</p> : null}
              {canForce ? (
                <div className="mt-2 space-y-1">
                  <p className="font-medium">Hapus paksa beserta seluruh transaksi (AR, kuitansi, jurnal, booking fee, biaya, kontrak, komisi). Unit kembali tersedia. Wajib alasan (≥10 huruf):</p>
                  <Textarea data-testid={`${testId}-force-reason`} rows={2} className="bg-background text-foreground"
                    placeholder="Alasan penghapusan (mis. data uji / salah input)" value={reason}
                    onChange={(e) => setReason(e.target.value)} />
                </div>
              ) : (
                <p className="mt-1 italic">Batalkan transaksi/pekerjaan terkait dulu, atau minta Direksi/Super Admin melakukan hapus paksa.</p>
              )}
            </div>
          ) : null}
          {check && !needForce && check.can_delete ? (
            <p data-testid={`${testId}-ok`} className="rounded-md border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-900">
              Tidak ada jejak transaksi — aman dihapus.
            </p>
          ) : null}
          <DialogFooter>
            <Button data-testid={`${testId}-cancel`} variant="outline" disabled={busy} onClick={() => setOpen(false)}>Batal</Button>
            <Button data-testid={`${testId}-confirm`} variant="destructive" disabled={busy || !canSubmit} onClick={run}>
              {busy ? "Menghapus…" : (needForce ? "Hapus paksa" : "Hapus")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
