import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import PhotoUploader from "@/components/patterns/PhotoUploader";
import api from "@/services/apiClient";
import * as sync from "@/services/offlineSync";
import { P50 } from "@/constants/testIds";

const MIN_REASON = 10;

/**
 * Dialog pengajuan klaim garansi (Fase 50A).
 *
 * Klaim yang bagiannya sudah lewat masa garansi TIDAK ditolak diam-diam di layar: kiriman
 * tetap dikirim ke server, dan server menjawab dengan klaim BERSTATUS DITOLAK beserta
 * tanggal habisnya. Dengan begitu pembeli menerima jawaban tertulis yang bisa diperiksa,
 * bukan tombol yang menolak tanpa jejak.
 */
export function ClaimCreateDialog({ open, unitId, unitCode, complaintId, onOpenChange, onDone }) {
  const [form, setForm] = useState({ category: "", source: "internal", title: "",
    description: "" });
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) {
      setForm({ category: "", source: complaintId ? "komplain_cs" : "internal", title: "",
        description: "" });
      setPhotos([]);
    }
  }, [open, complaintId]);

  const valid = form.category && form.title.trim().length >= 4;

  const submit = async () => {
    setBusy(true);
    try {
      const out = await sync.submitOrQueue({
        kind: "warranty_claim",
        payload: {
          unit_id: unitId, category: form.category, source: form.source,
          title: form.title.trim(), description: form.description.trim() || null,
          complaint_id: complaintId || null,
        },
        photos,
        title: `${unitCode || ""} · ${form.title.slice(0, 40)}`,
      });
      if (out.queued) {
        toast.success("Klaim tersimpan di perangkat — terkirim sendiri begitu sinyal kembali.");
      } else {
        toast.success(out.res?.data?.message || "Klaim garansi tercatat.");
      }
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengajukan klaim garansi.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P50.claimDialog} className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Ajukan klaim garansi {unitCode ? `— ${unitCode}` : ""}</DialogTitle>
          <DialogDescription>
            Pilih bagian pekerjaan yang dikeluhkan. Bila masa garansi bagian itu sudah lewat,
            klaim tetap tercatat dengan jawaban tertulis beserta tanggal habisnya.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Bagian yang dikeluhkan</Label>
            <ReferenceSelect group="warranty_category" value={form.category}
              onChange={(v) => set("category", v)} testId={P50.claimCategory} />
          </div>
          <div className="space-y-1.5">
            <Label>Asal klaim</Label>
            <ReferenceSelect group="warranty_claim_source" value={form.source}
              onChange={(v) => set("source", v)} testId={P50.claimSource} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="claim-title">Judul keluhan</Label>
            <Input id="claim-title" data-testid={P50.claimTitle} value={form.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="mis. plafon kamar depan bocor saat hujan" />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="claim-desc">Uraian (opsional)</Label>
            <Textarea id="claim-desc" rows={3} data-testid={P50.claimDescription}
              value={form.description} onChange={(e) => set("description", e.target.value)}
              placeholder="Ceritakan sejak kapan, di bagian mana, dan seberapa parah." />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Foto keluhan (opsional)</Label>
            <PhotoUploader value={photos} onChange={setPhotos} ownerType="build" max={4}
              testId="p50-claim-photos" label="Tambah foto keluhan" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={busy} data-testid={P50.claimCancel}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={P50.claimSubmit} onClick={submit} disabled={busy || !valid}>
            {busy ? "Mengirim…" : "Ajukan klaim"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Satu dialog untuk semua keputusan atas klaim (Fase 50A): terima, tolak, selesai (dengan
 * bukti foto WAJIB), periksa/kembalikan, dan tutup dengan pengakuan pembeli.
 *
 * Aturan yang dijaga di layar SAMA dengan yang dijaga server — tombol nonaktif kalau
 * syaratnya belum terpenuhi, supaya pemakai tahu sebelum menekan, bukan sesudah gagal.
 */
export function ClaimActionDialog({ mode, claim, open, onOpenChange, onDone }) {
  const [reason, setReason] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [assignee, setAssignee] = useState("");
  const [ack, setAck] = useState("");
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setReason(""); setRejectReason(""); setAssignee(claim?.assigned_to || "");
      setAck(claim?.buyer_name || ""); setPhotos([]);
    }
  }, [open, claim]);

  if (!claim) return null;
  const reasonOk = reason.trim().length >= MIN_REASON;
  const title = {
    accept: `Terima klaim ${claim.number}`,
    reject: `Tolak klaim ${claim.number}`,
    complete: `Perbaikan selesai — ${claim.number}`,
    verify: `Periksa hasil perbaikan ${claim.number}`,
    rework: `Kembalikan perbaikan ${claim.number}`,
    close: `Tutup klaim ${claim.number}`,
  }[mode] || "Klaim garansi";

  const canSubmit = {
    accept: true,
    reject: reasonOk && !!rejectReason,
    complete: photos.length > 0,
    verify: true,
    rework: reasonOk,
    close: true,
  }[mode];

  const submit = async () => {
    setBusy(true);
    try {
      let res;
      if (mode === "accept") {
        res = await api.post(`/handover/claims/${claim.id}/decide`, {
          accept: true, reason: reason.trim() || null,
          assigned_to: assignee.trim() || null });
      } else if (mode === "reject") {
        res = await api.post(`/handover/claims/${claim.id}/decide`, {
          accept: false, reason: reason.trim(), reject_reason: rejectReason });
      } else if (mode === "complete") {
        const out = await sync.submitOrQueue({
          kind: "warranty_fix",
          endpoint: `/handover/claims/${claim.id}/complete`,
          payload: { note: reason.trim() || null },
          photos,
          title: `Bukti perbaikan ${claim.number}`,
        });
        if (out.queued) {
          toast.success("Bukti perbaikan tersimpan di perangkat — terkirim sendiri begitu "
            + "sinyal kembali.");
          onOpenChange(false); onDone?.();
          return;
        }
        res = out.res;
      } else if (mode === "verify") {
        res = await api.post(`/handover/claims/${claim.id}/verify`, {
          passed: true, note: reason.trim() || null });
      } else if (mode === "rework") {
        res = await api.post(`/handover/claims/${claim.id}/verify`, {
          passed: false, reason: reason.trim() });
      } else {
        res = await api.post(`/handover/claims/${claim.id}/close`, {
          ack_by: ack.trim() || null, ack_note: reason.trim() || null });
      }
      toast.success(res?.data?.message || "Klaim diperbarui.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Gagal memperbarui klaim garansi.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P50.claimActionDialog}
        className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {claim.category_label} · {claim.unit_code} · {claim.title}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {mode === "reject" ? (
            <div className="space-y-1.5">
              <Label>Sebab penolakan</Label>
              <ReferenceSelect group="warranty_reject_reason" value={rejectReason}
                onChange={setRejectReason} testId={P50.claimActionRejectReason} />
            </div>
          ) : null}
          {mode === "accept" ? (
            <div className="space-y-1.5">
              <Label htmlFor="claim-assignee">Ditugaskan kepada (email, opsional)</Label>
              <Input id="claim-assignee" data-testid={P50.claimActionAssignee}
                value={assignee} onChange={(e) => setAssignee(e.target.value)}
                placeholder="kosongkan agar sistem memilih Manajer Proyek" />
            </div>
          ) : null}
          {mode === "complete" ? (
            <div className="space-y-1.5">
              <Label>Bukti foto perbaikan (wajib)</Label>
              <PhotoUploader value={photos} onChange={setPhotos} ownerType="build" max={4}
                testId={P50.claimActionPhotos} label="Tambah foto sesudah" />
              {!photos.length ? (
                <p className="text-[11px] text-rose-700">
                  Perbaikan tidak bisa dinyatakan selesai tanpa bukti foto.
                </p>
              ) : null}
            </div>
          ) : null}
          {mode === "close" ? (
            <div className="space-y-1.5">
              <Label htmlFor="claim-ack">Pengakuan dari (nama pembeli)</Label>
              <Input id="claim-ack" data-testid={P50.claimActionAck} value={ack}
                onChange={(e) => setAck(e.target.value)} />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="claim-reason">
              {mode === "reject" || mode === "rework"
                ? `Alasan (minimal ${MIN_REASON} huruf)`
                : "Catatan (opsional)"}
            </Label>
            <Textarea id="claim-reason" rows={3} data-testid={P50.claimActionReason}
              value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder={mode === "reject"
                ? "mis. kerusakan akibat perubahan instalasi oleh pemilik"
                : "mis. retak disuntik epoxy lalu diaci ulang"} />
            {(mode === "reject" || mode === "rework") ? (
              <p className={`text-[11px] ${reasonOk ? "text-muted-foreground" : "text-rose-700"}`}>
                {reason.trim().length}/{MIN_REASON} huruf — alasan ini dibaca pembeli.
              </p>
            ) : null}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={busy} data-testid={P50.claimActionCancel}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={P50.claimActionSubmit} onClick={submit}
            disabled={busy || !canSubmit}
            variant={mode === "reject" || mode === "rework" ? "destructive" : "default"}>
            {busy ? "Memproses…" : {
              accept: "Terima & buat pekerjaan",
              reject: "Tolak klaim",
              complete: "Nyatakan selesai",
              verify: "Lulus pemeriksaan",
              rework: "Kembalikan untuk diulang",
              close: "Tutup klaim",
            }[mode]}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
