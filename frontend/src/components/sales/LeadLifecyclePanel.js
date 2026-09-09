import React, { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Circle, ArrowRight, ShieldAlert, Sparkles, History,
  ThumbsUp, Minus, ThumbsDown, PhoneOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import LeadSlikPanel from "@/components/sales/LeadSlikPanel";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LEADS } from "@/constants/testIds";
import { cn } from "@/lib/utils";
import { useReference } from "@/context/ReferenceContext";
import ReferenceItems from "@/components/patterns/ReferenceItems";

// Ikon per nilai; LABEL & daftar nilai tetap dari SSOT backend (grup 'lead_disposition').
const DISPOSITION_ICON = {
  positive: { icon: ThumbsUp, tone: "text-emerald-600" },
  neutral: { icon: Minus, tone: "text-amber-600" },
  negative: { icon: ThumbsDown, tone: "text-rose-600" },
  no_response: { icon: PhoneOff, tone: "text-muted-foreground" },
};

/**
 * LeadLifecyclePanel — tahap lead sebagai GERBANG BUKTI + pemandu langkah berikutnya.
 *
 * Dulu: satu dropdown "Ubah Stage" bebas — sales bisa menaruh lead di 'booking' tanpa
 * reservasi, atau 'won' tanpa akad; laporan funnel jadi tidak bisa dipercaya.
 * Sekarang: checklist syarat per tahap (diperiksa pada data), tombol maju hanya aktif bila
 * syarat lengkap, penutupan wajib beralasan, dan override hanya untuk supervisor.
 */
export default function LeadLifecyclePanel({ lead, lifecycle, onAction, onChanged }) {
  const { labelOf, options } = useReference();
  const [busy, setBusy] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [closeStage, setCloseStage] = useState("lost");
  const [closeReason, setCloseReason] = useState("");
  const [closeNote, setCloseNote] = useState("");
  const [ovOpen, setOvOpen] = useState(false);
  const [ovStage, setOvStage] = useState("");
  const [ovReason, setOvReason] = useState("");
  const [dispNote, setDispNote] = useState("");

  if (!lifecycle) return null;
  const { stage, order, next_stage: next, can_advance: canAdvance, blocked_reason: blocked,
          requirements = {}, next_actions: actions = [], history = [], reasons = [],
          can_override: canOverride } = lifecycle;
  const nextReqs = (next && requirements[next]) || [];
  const idx = order.indexOf(stage);

  const run = async (fn, okMsg) => {
    setBusy(true);
    try {
      await fn();
      toast.success(okMsg);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal.");
    } finally { setBusy(false); }
  };

  const advance = () => run(
    () => api.post(`/leads/${lead.id}/stage`, { stage: next }),
    `Tahap lead naik ke ${labelOf("lead_stage", next)}.`);

  const closeLead = () => {
    if (!closeReason) { toast.error("Pilih alasan."); return; }
    const label = reasons.find((r) => r.value === closeReason)?.label || closeReason;
    const note = closeNote.trim() ? `${label} — ${closeNote.trim()}` : label;
    run(() => api.post(`/leads/${lead.id}/stage`, { stage: closeStage, note }),
        "Lead ditutup dengan alasan tercatat.").then(() => setCloseOpen(false));
  };

  const override = () => {
    if (!ovStage || ovReason.trim().length < 5) {
      toast.error("Pilih tahap & tulis alasan (minimal 5 karakter).");
      return;
    }
    run(() => api.post(`/leads/${lead.id}/stage/override`, { stage: ovStage, reason: ovReason }),
        "Tahap diubah paksa (tercatat di riwayat).").then(() => setOvOpen(false));
  };

  const setDisposition = (value) => run(
    () => api.post(`/leads/${lead.id}/disposition`,
                   { disposition: value, note: dispNote || null }),
    "Penilaian respons lead disimpan.");

  return (
    <div data-testid={LEADS.lifecycle} className="space-y-3">
      {/* Stepper tahap */}
      <div data-testid={LEADS.stepper} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-center gap-1.5">
          {order.map((s, i) => (
            <React.Fragment key={s}>
              <span data-testid={`${LEADS.stepPrefix}-${s}`}
                data-active={i === idx ? "1" : "0"}
                className={cn("rounded-full px-2.5 py-1 text-xs font-medium",
                  i < idx ? "bg-emerald-100 text-emerald-800"
                    : i === idx ? "bg-primary text-primary-foreground"
                      : "bg-secondary text-muted-foreground")}>
                {labelOf("lead_stage", s)}
              </span>
              {i < order.length - 1 ? (
                <ArrowRight className="h-3 w-3 text-muted-foreground" />
              ) : null}
            </React.Fragment>
          ))}
          {["lost", "recycle"].includes(stage) ? (
            <StatusPill status={stage} group="lead_stage" />
          ) : null}
        </div>

        {next ? (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-semibold uppercase text-muted-foreground">
              Syarat naik ke {labelOf("lead_stage", next)}
            </p>
            {nextReqs.map((r) => (
              <div key={r.key} data-testid={LEADS.requirement} data-met={r.met ? "1" : "0"}
                className="flex items-center justify-between gap-2 rounded-lg border bg-card px-2.5 py-1.5 shadow-[var(--shadow-card)]">
                <span className="flex items-center gap-2 text-xs">
                  {r.met ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    : <Circle className="h-4 w-4 text-muted-foreground" />}
                  {r.label}
                </span>
                {!r.met ? (
                  <Button size="sm" variant="outline" className="h-7 text-xs"
                    onClick={() => onAction && onAction(r.link)}>{r.action}</Button>
                ) : null}
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button size="sm" data-testid={LEADS.advanceBtn} disabled={busy || !canAdvance}
                onClick={advance}>
                Naikkan ke {labelOf("lead_stage", next)}
              </Button>
              <Button size="sm" variant="outline" data-testid={LEADS.closeBtn}
                onClick={() => setCloseOpen(true)} disabled={busy}>
                Tandai Hilang / Daur Ulang
              </Button>
              {canOverride ? (
                <Button size="sm" variant="ghost" data-testid={LEADS.overrideBtn}
                  onClick={() => setOvOpen(true)} disabled={busy}>
                  <ShieldAlert className="mr-1.5 h-3.5 w-3.5" /> Override (supervisor)
                </Button>
              ) : null}
            </div>
            {!canAdvance && blocked ? (
              <p data-testid={LEADS.blockedNote}
                className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">
                {blocked}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 text-xs text-muted-foreground">
            {stage === "won" ? "Lead sudah menang (akad/AJB selesai)."
              : "Tahap akhir. Gunakan Daur Ulang bila ingin menghidupkan kembali lead ini."}
          </p>
        )}
      </div>

      {/* Pra-skrining BI/SLIK berbukti — gerbang wajib sebelum booking (Fase 30a) */}
      <LeadSlikPanel lead={lead} lifecycle={lifecycle} onChanged={onChanged} />

      {/* Penilaian kualitatif respons lead */}
      <div data-testid={LEADS.dispositionBar} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
          Respons lead (penilaian agen)
          {lifecycle.disposition ? (
            <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium normal-case text-foreground">
              {labelOf("lead_disposition", lifecycle.disposition)}
            </span>
          ) : null}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {options("lead_disposition").map((d) => {
            const meta = DISPOSITION_ICON[d.value] || {};
            const Icon = meta.icon || Minus;
            const active = lifecycle.disposition === d.value;
            return (
              <Button key={d.value} size="sm" variant={active ? "default" : "outline"}
                data-testid={`${LEADS.dispositionPrefix}-${d.value}`} disabled={busy}
                onClick={() => setDisposition(d.value)}>
                <Icon className={cn("mr-1.5 h-3.5 w-3.5", active ? "" : meta.tone)} /> {d.label}
              </Button>
            );
          })}
        </div>
        <Textarea data-testid={LEADS.dispositionNote} rows={2} className="mt-2"
          placeholder="Catatan kualitatif: apa yang dikatakan lead, kendalanya, dsb."
          value={dispNote} onChange={(e) => setDispNote(e.target.value)} />
        {lifecycle.disposition_note ? (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Catatan terakhir: {lifecycle.disposition_note}
          </p>
        ) : null}
      </div>

      {/* Langkah berikutnya */}
      {actions.length ? (
        <div data-testid={LEADS.nba} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" /> Langkah berikutnya
          </p>
          <div className="space-y-1.5">
            {actions.map((a) => (
              <button key={a.key} type="button" data-testid={LEADS.nbaItem}
                onClick={() => onAction && onAction(a.key)}
                className="flex w-full items-center justify-between gap-2 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors hover:bg-secondary/60 shadow-[var(--shadow-card)]">
                <span>
                  <span className="block text-sm font-medium">{a.label}</span>
                  <span className="block text-[11px] text-muted-foreground">{a.reason}</span>
                </span>
                <StatusPill status={a.priority} group="priority" />
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* Riwayat tahap */}
      {history.length ? (
        <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
            <History className="h-3.5 w-3.5" /> Riwayat tahap ({history.length})
          </p>
          <div className="space-y-1.5">
            {history.slice().reverse().map((h, i) => (
              <div key={i} data-testid={LEADS.historyItem}
                className="rounded-lg bg-secondary/50 px-2.5 py-1.5 text-xs">
                <span className="font-medium">
                  {labelOf("lead_stage", h.from)} → {labelOf("lead_stage", h.to)}
                </span>
                {h.override ? (
                  <span className="ml-1.5 rounded bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-800">
                    OVERRIDE
                  </span>
                ) : null}
                <span className="block text-[11px] text-muted-foreground">
                  {formatDateTimeWIB(h.at)} · {h.actor}{h.reason ? ` · ${h.reason}` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Dialog tutup lead */}
      <Dialog open={closeOpen} onOpenChange={setCloseOpen}>
        <DialogContent className="bg-background">
          <DialogHeader>
            <DialogTitle>Tandai Hilang / Daur Ulang</DialogTitle>
            <DialogDescription>
              Alasan WAJIB diisi — dipakai untuk menganalisis kebocoran pipeline.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Tahap</Label>
              <Select value={closeStage} onValueChange={setCloseStage}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <ReferenceItems group="lead_stage" only={["lost", "recycle"]} />
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Alasan</Label>
              <Select value={closeReason} onValueChange={setCloseReason}>
                <SelectTrigger data-testid={LEADS.closeReason}>
                  <SelectValue placeholder="Pilih alasan…" />
                </SelectTrigger>
                <SelectContent>
                  {reasons.map((r) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="leadlifecyclepanel-keterangan-tambahan">Keterangan tambahan</Label>
              <Textarea id="leadlifecyclepanel-keterangan-tambahan" rows={2} value={closeNote} onChange={(e) => setCloseNote(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCloseOpen(false)} disabled={busy}>Batal</Button>
            <Button data-testid={LEADS.closeSubmit} onClick={closeLead} disabled={busy || !closeReason}>
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog override supervisor */}
      <Dialog open={ovOpen} onOpenChange={setOvOpen}>
        <DialogContent className="bg-background">
          <DialogHeader>
            <DialogTitle>Override tahap (supervisor)</DialogTitle>
            <DialogDescription>
              Dipakai untuk data lama/koreksi. Tercatat permanen di riwayat tahap.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Tahap tujuan</Label>
              <Select value={ovStage} onValueChange={setOvStage}>
                <SelectTrigger data-testid={LEADS.overrideStage}>
                  <SelectValue placeholder="Pilih tahap…" />
                </SelectTrigger>
                <SelectContent>
                  {[...order, "recycle", "lost"].filter((s) => s !== stage).map((s) => (
                    <SelectItem key={s} value={s}>{labelOf("lead_stage", s)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="leadlifecyclepanel-alasan-wajib">Alasan (wajib)</Label>
              <Textarea id="leadlifecyclepanel-alasan-wajib" data-testid={LEADS.overrideReason} rows={2} value={ovReason}
                onChange={(e) => setOvReason(e.target.value)}
                placeholder="mis. migrasi data lama; akad sudah dilakukan di luar sistem" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOvOpen(false)} disabled={busy}>Batal</Button>
            <Button data-testid={LEADS.overrideSubmit} onClick={override} disabled={busy}>
              Terapkan Override
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
