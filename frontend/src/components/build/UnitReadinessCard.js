import React, { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, Info, PlayCircle, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { READINESS_TONE, SEVERITY_TONE } from "@/utils/permitUi";
import { READINESS } from "@/constants/testIds";

const ICON = { blocker: AlertTriangle, warning: ShieldAlert, info: Info };

/**
 * KARTU KESIAPAN MULAI BANGUN (Fase 46, dok 29 §2).
 *
 * Prinsip UX yang dipegang: **tidak ada tombol mati tanpa penjelasan**. Setiap alasan
 * ditampilkan dengan tingkatnya (menghalangi / peringatan / informasi) dan cara
 * memperbaikinya. Bila hanya ada peringatan, tombol TETAP bisa ditekan — tetapi pemakai
 * wajib mencentang pengakuan + menulis alasan, dan keputusan itu tercatat di jejak unit.
 */
export default function UnitReadinessCard({ readiness, canStart, onChanged }) {
  const [open, setOpen] = useState(false);
  const [ack, setAck] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  if (!readiness) return null;

  const { state, reasons = [], warnings = [], blockers = [], checks = {}, mode = {},
    missing = [] } = readiness;
  const pay = checks.payment || {};
  const permits = checks.permits || {};
  const needAck = readiness.needs_ack;
  const problems = [];
  if (needAck && !ack) problems.push("Centang pengakuan peringatan lebih dulu.");
  if (needAck && reason.trim().length < 5) problems.push("Alasan minimal 5 huruf.");

  const run = async () => {
    if (problems.length) { toast.error(problems[0]); return; }
    setBusy(true);
    try {
      const r = await api.post(`/build/unit/${readiness.unit_id}/start`,
        { ack, reason: reason.trim() || null });
      toast.success(r.data?.message || "Pembangunan dimulai.");
      setOpen(false); setAck(false); setReason("");
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memulai pembangunan.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={READINESS.card} data-state={state}
      className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Kesiapan mulai bangun
          </p>
          <div className="mt-1 flex items-center gap-2" data-testid={READINESS.state}>
            <StatusPill status={state} group="build_readiness_state"
              tone={READINESS_TONE[state]} />
            <span className="text-sm text-muted-foreground">
              unit {readiness.unit_code}
            </span>
          </div>
        </div>
        {canStart && state !== "started" ? (
          <Button size="sm" data-testid={READINESS.startBtn} onClick={() => setOpen(true)}
            disabled={!readiness.can_start}>
            <PlayCircle className="mr-1.5 h-4 w-4" /> Mulai bangun
          </Button>
        ) : null}
      </div>

      <p data-testid={READINESS.mode} className="mt-2 text-xs text-muted-foreground">
        Kebijakan aktif: {mode.require_dp_before_start
          ? "DP wajib terbayar — mulai bangun DIBLOKIR bila belum"
          : "DP belum terbayar hanya jadi PERINGATAN (bawaan)"}
        {mode.block_build_without?.length
          ? ` · izin wajib: ${mode.block_build_without.join(", ")}`
          : " · tidak ada izin yang memblokir"}
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div data-testid={READINESS.payment} className="rounded-lg border bg-secondary p-2.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Termin pertama (DP)
          </p>
          {!pay.known ? (
            <p className="text-sm font-medium">belum ada data</p>
          ) : (
            <p className="text-sm font-medium">
              {pay.label} · {pay.paid ? "sudah terbayar" : "belum terbayar"}
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">
            {pay.known
              ? `${formatIDR(pay.paid_amount)} dari ${formatIDR(pay.amount)}`
              : "Unit ini belum punya rencana bayar (termin)."}
          </p>
        </div>
        <div data-testid={READINESS.permits} className="rounded-lg border bg-secondary p-2.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Izin yang berlaku untuk unit ini
          </p>
          {permits.state === "empty" ? (
            <p className="text-sm font-medium">belum ada data</p>
          ) : (
            <p className="text-sm font-medium">
              {permits.total} izin · {permits.counts?.expiring || 0} menjelang kedaluwarsa ·{" "}
              {permits.counts?.expired || 0} kedaluwarsa
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">
            Termasuk izin warisan dari blok, cluster, dan proyek.
          </p>
        </div>
      </div>

      {reasons.length ? (
        <ul className="mt-3 space-y-2">
          {reasons.map((r, i) => {
            const Icon = ICON[r.severity] || Info;
            return (
              <li key={`${r.code}-${i}`} data-testid={READINESS.reason}
                data-code={r.code} data-severity={r.severity}
                className={`rounded-lg border p-2.5 text-xs ${SEVERITY_TONE[r.severity]}`}>
                <p className="flex items-center gap-1.5 font-semibold">
                  <Icon className="h-3.5 w-3.5" /> {r.label}
                  <span className="rounded bg-white/60 px-1 text-[10px]">
                    {r.severity_label}
                  </span>
                </p>
                <p className="mt-1">{r.detail}</p>
                {r.fix ? <p className="mt-1 italic">Cara memperbaiki: {r.fix}</p> : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-3 flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-900">
          <CheckCircle2 className="h-3.5 w-3.5" /> Tidak ada penghalang maupun peringatan —
          unit siap dimulai.
        </p>
      )}

      {missing.length ? (
        <p data-testid={READINESS.missing} className="mt-2 text-[11px] text-muted-foreground">
          Data yang belum ada: {missing.join(", ")}. Angka yang bergantung padanya ditulis
          “belum ada data”, bukan nol.
        </p>
      ) : null}

      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setAck(false); } }}>
        <DialogContent data-testid={READINESS.dialog} className="bg-card sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Mulai bangun unit {readiness.unit_code}</DialogTitle>
            <DialogDescription>
              Langkah pertama yang sudah terbuka akan ditandai sedang dikerjakan, sehingga
              progres unit lahir dari pekerjaan nyata — bukan status yang ditimpa.
            </DialogDescription>
          </DialogHeader>
          {blockers.length ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900">
              <p className="font-semibold">Masih ada penghalang:</p>
              <ul className="mt-1 list-disc pl-4">
                {blockers.map((b, i) => <li key={i}>{b.detail}</li>)}
              </ul>
            </div>
          ) : null}
          {warnings.length ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                <p className="font-semibold">
                  {warnings.length} peringatan — boleh dilanjutkan, tetapi harus diakui:
                </p>
                <ul className="mt-1 list-disc pl-4">
                  {warnings.map((w, i) => <li key={i}>{w.detail}</li>)}
                </ul>
              </div>
              <label className="flex items-start gap-2 text-xs">
                <Checkbox data-testid={READINESS.ack} checked={ack}
                  onCheckedChange={(v) => setAck(!!v)} />
                <span>
                  Saya mengakui peringatan di atas dan bertanggung jawab atas keputusan
                  memulai pembangunan sekarang.
                </span>
              </label>
              <div className="space-y-1.5">
                <Label htmlFor="start-reason">Alasan (wajib, minimal 5 huruf)</Label>
                <Textarea id="start-reason" rows={3} data-testid={READINESS.reasonInput}
                  value={reason} onChange={(e) => setReason(e.target.value)}
                  placeholder="mis. disetujui direksi: pondasi didahulukan sebelum musim hujan" />
              </div>
              {problems.length ? (
                <p className="text-xs text-rose-700">{problems[0]}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Tidak ada peringatan — pembangunan bisa langsung dimulai.
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Batal
            </Button>
            <Button data-testid={READINESS.submit} onClick={run}
              disabled={busy || !!blockers.length || !!problems.length}>
              {busy ? "Memproses…" : "Mulai bangun"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
