import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, FileText, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import { formatDateWIB } from "@/utils/formatters";
import api, { API } from "@/services/apiClient";
import { INTAKE } from "@/constants/testIds";

const MIN_REJECT = 10;

/**
 * IntakeReviewDialog — finance melihat bukti transfer lalu MEMUTUSKAN.
 *
 * Yang membuat keputusan ini bisa dipertanggungjawabkan:
 *   * lampiran bukti bisa DIBUKA (bukan hanya nama berkas);
 *   * verifikasi memakai jalur resmi `apply_receipt` — tagihan berkurang tepat sekali dan
 *     kuitansinya bisa ditelusuri;
 *   * kelebihan bayar tidak boleh “hilang”: bila nominal melebihi sisa tagihan, kasir harus
 *     SENGAJA mencentang bahwa kelebihannya dicatat sebagai titipan pelanggan;
 *   * penolakan wajib beralasan minimal {MIN_REJECT} huruf karena alasannya dibaca pelanggan
 *     di Portal (bukan catatan internal).
 */
export default function IntakeReviewDialog({ intake, open, onOpenChange, onDone,
  canDecide = true }) {
  const [mode, setMode] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [overpay, setOverpay] = useState(false);
  const [busy, setBusy] = useState(false);
  const token = localStorage.getItem("sipro_token");

  useEffect(() => {
    if (open) { setMode(""); setReason(""); setNote(""); setOverpay(false); }
  }, [open, intake?.id]);

  if (!intake) return null;
  const pending = intake.state === "pending";
  // `canDecide` = izin efektif `finance:approve` dari layar pemanggil. Tanpa itu dialog hanya
  // MENAMPILKAN bukti (peran lain tetap boleh menelusuri) tanpa tombol yang pasti dijawab 403;
  // keterangan "tagihan belum berkurang" tetap terbaca semua peran.
  const canAct = pending && canDecide;

  const verify = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/payment-intakes/${intake.id}/verify`, {
        note: note.trim() || null, allow_overpay: overpay,
      });
      toast.success(res.data.message || "Bukti diverifikasi — tagihan berkurang.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memverifikasi bukti transfer.");
    } finally { setBusy(false); }
  };

  const reject = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/payment-intakes/${intake.id}/reject`,
        { reason: reason.trim() });
      toast.success(res.data.message || "Bukti ditolak — alasan dikirim ke pelanggan.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menolak bukti transfer.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={INTAKE.reviewDialog} className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Bukti transfer · {intake.customer_name}</DialogTitle>
          <DialogDescription>
            Unit {intake.unit_code || "-"} · transfer {formatDateWIB(intake.transfer_date)}
            {intake.bank_name ? ` · ${intake.bank_name}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-xs text-muted-foreground">Nominal diklaim</p>
              <MoneyText value={intake.amount} className="font-heading text-lg font-semibold" />
            </div>
            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-xs text-muted-foreground">Sisa tagihan saat dikirim</p>
              {intake.outstanding_at_submit === null
                || intake.outstanding_at_submit === undefined ? (
                  <p className="text-sm text-muted-foreground">belum ada data</p>
                ) : <MoneyText value={intake.outstanding_at_submit}
                  className="font-heading text-lg font-semibold" />}
            </div>
            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-xs text-muted-foreground">Status</p>
              <div className="mt-1"><StatusPill status={intake.state} group="payment_intake_state" /></div>
            </div>
          </div>

          <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
            <p className="text-xs font-medium text-muted-foreground">Lampiran bukti</p>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {(intake.files || []).map((f, i) => (f.id ? (
                <a key={f.id} data-testid={INTAKE.proofLink}
                  href={`${API}/files/${f.id}?auth=${token || ""}`} target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-xs font-medium hover:bg-accent">
                  <FileText className="h-3.5 w-3.5" /> {f.filename || "bukti"}
                </a>
              ) : (
                <span key={i} className="inline-flex items-center gap-1.5 rounded-md border border-dashed px-2 py-1 text-xs text-muted-foreground">
                  <FileText className="h-3.5 w-3.5" /> {f.filename || "bukti"} (berkas contoh, tidak tersimpan)
                </span>
              )))}
              {!(intake.files || []).length ? (
                <span className="text-xs text-muted-foreground">Tidak ada lampiran.</span>
              ) : null}
            </div>
            {intake.note ? (
              <p className="mt-2 text-sm">Catatan pelanggan: {intake.note}</p>
            ) : null}
          </div>

          {pending ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Selama masih menunggu, tagihan pelanggan BELUM berkurang. Verifikasi akan
              membuat kuitansi resmi; penolakan tidak menyentuh tagihan sama sekali.
            </p>
          ) : null}

          {canAct && mode === "verify" ? (
            <div className="space-y-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <div className="space-y-1.5">
                <Label htmlFor="intake-note">Catatan verifikasi (opsional)</Label>
                <Textarea id="intake-note" rows={2} value={note} className="bg-background"
                  placeholder="Mis. cocok dengan mutasi rekening 16 Agustus."
                  onChange={(e) => setNote(e.target.value)} />
              </div>
              <label className="flex items-start gap-2 text-sm">
                <Checkbox data-testid={INTAKE.overpayCheck} checked={overpay}
                  onCheckedChange={(v) => setOverpay(!!v)} />
                <span>
                  Catat kelebihan sebagai <b>titipan pelanggan</b> bila nominal melebihi sisa
                  tagihan (tanpa ini, kelebihan bayar ditolak agar kas tidak pernah salah).
                </span>
              </label>
            </div>
          ) : null}

          {canAct && mode === "reject" ? (
            <div className="space-y-1.5 rounded-lg border border-rose-200 bg-rose-50 p-3">
              <Label htmlFor="intake-reject">
                Alasan penolakan (dibaca pelanggan, minimal {MIN_REJECT} huruf)
              </Label>
              <Textarea id="intake-reject" data-testid={INTAKE.rejectReason} rows={3}
                value={reason} className="bg-background"
                placeholder="Mis. nominal pada bukti tidak sama dengan mutasi yang kami terima."
                onChange={(e) => setReason(e.target.value)} />
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Tutup</Button>
          {canAct && mode !== "verify" ? (
            <Button variant="destructive" data-testid={INTAKE.rejectBtn}
              disabled={busy || (mode === "reject" && reason.trim().length < MIN_REJECT)}
              onClick={() => (mode === "reject" ? reject() : setMode("reject"))}>
              <XCircle className="mr-1.5 h-4 w-4" />
              {mode === "reject" ? "Kirim penolakan" : "Tolak"}
            </Button>
          ) : null}
          {canAct && mode !== "reject" ? (
            <Button data-testid={INTAKE.verifyBtn} disabled={busy}
              onClick={() => (mode === "verify" ? verify() : setMode("verify"))}>
              <CheckCircle2 className="mr-1.5 h-4 w-4" />
              {mode === "verify" ? "Verifikasi & catat kuitansi" : "Verifikasi"}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
