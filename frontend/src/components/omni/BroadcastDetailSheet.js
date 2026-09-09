import React from "react";
import { toast } from "sonner";
import { Ban, Pause, Play, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import { formatDateTimeWIB, formatIDR, formatNumber } from "@/utils/formatters";
import api from "@/services/apiClient";
import { OMNI, P97 } from "@/constants/testIds";

const COUNTS = [
  ["total", "Penerima", ""], ["queued", "Antre", "text-sky-700"], ["sent", "Terkirim", "text-emerald-700"],
  ["simulated", "Simulasi", "text-zinc-600"], ["delivered", "Sampai", "text-emerald-700"],
  ["read", "Dibaca", "text-indigo-700"], ["failed", "Gagal", "text-rose-700"], ["skipped", "Dilewati", "text-amber-700"],
];

/** Tombol jeda / lanjut / batal / proses sekarang — dipakai di kartu daftar dan sheet detail. */
export function BroadcastActions({ b, canManage, onChanged, size = "sm" }) {
  if (!canManage) return null;
  const act = async (action) => {
    try {
      const r = await api.post(`/broadcasts/${b.id}/${action}`);
      if (action === "run") {
        const run = r.data.data.run;
        toast.success(run.skipped_window ? run.notes[0] : `Antrean diproses: ${run.processed} pesan (${run.simulated} simulasi, ${run.sent} terkirim, ${run.failed} gagal).`);
      } else toast.success({ pause: "Broadcast dijeda.", resume: "Broadcast dilanjutkan.", cancel: "Broadcast dibatalkan; sisa antrean dihentikan." }[action]);
      onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Aksi gagal."); }
  };
  const live = ["queued", "sending"].includes(b.status);
  return (
    <div className="flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
      {live ? <Button data-testid={P97.bcRunBtn} size={size} variant="outline" onClick={() => act("run")} title="Proses antrean sekarang"><Zap className="h-3.5 w-3.5" /> Proses</Button> : null}
      {live ? <Button data-testid={P97.bcPauseBtn} size={size} variant="outline" onClick={() => act("pause")}><Pause className="h-3.5 w-3.5" /> Jeda</Button> : null}
      {b.status === "paused" ? <Button data-testid={P97.bcResumeBtn} size={size} variant="outline" onClick={() => act("resume")}><Play className="h-3.5 w-3.5" /> Lanjut</Button> : null}
      {["queued", "sending", "paused"].includes(b.status) ? <Button data-testid={P97.bcCancelBtn} size={size} variant="ghost" className="text-destructive" onClick={() => act("cancel")}><Ban className="h-3.5 w-3.5" /> Batal</Button> : null}
    </div>
  );
}

export function BroadcastCounts({ b }) {
  return (
    <p data-testid={P97.bcCounts} className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
      {COUNTS.filter(([k]) => k === "total" || b[k]).map(([k, l, cls]) => (
        <span key={k} className={cls}>{formatNumber(b[k] || 0)} {l}</span>
      ))}
      {b.cost_estimate ? <span data-testid={P97.bcCost}>· est. biaya {formatIDR(b.cost_estimate)}</span> : null}
    </p>
  );
}

export default function BroadcastDetailSheet({ detail, onOpenChange, canManage, onChanged }) {
  const b = detail?.broadcast;
  return (
    <Sheet open={!!detail} onOpenChange={(v) => !v && onOpenChange(false)}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        {b ? (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">{b.name} <StatusPill status={b.status} group="broadcast_status" /></SheetTitle>
              <SheetDescription>
                Template: {b.template_name} ({b.category}) · {formatDateTimeWIB(b.created_at)} · mode {b.mode}
                {b.scheduled_for ? <> · dijadwalkan {formatDateTimeWIB(b.scheduled_for)} (di luar jam kirim)</> : null}
              </SheetDescription>
            </SheetHeader>
            <div className="mt-3"><BroadcastActions b={b} canManage={canManage} onChanged={onChanged} /></div>
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              {COUNTS.map(([k, l, cls]) => (
                <div key={k} className="rounded-lg border bg-card p-2 shadow-[var(--shadow-card)]">
                  <p className={`text-lg font-semibold tabular-nums ${cls}`}>{formatNumber(b[k] || 0)}</p>
                  <p className="text-[11px] text-muted-foreground">{l}</p>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Sampai/Dibaca hanya berubah dari webhook status Meta — tidak ada angka karangan. Estimasi biaya {formatIDR(b.cost_estimate || 0)} ({formatIDR(b.unit_cost || 0)}/percakapan {b.category}).
            </p>
            {detail.failures?.length ? (
              <div data-testid={P97.bcFailures} className="mt-4 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="mb-1 text-xs font-medium">Kegagalan / dilewati per kode</p>
                {detail.failures.map((f) => (
                  <p key={f.code} className="flex justify-between text-xs"><span><code className="font-mono">{f.code}</code> — {f.detail}</span><b className="tabular-nums">{f.count}</b></p>
                ))}
              </div>
            ) : null}
            <div className="mt-4 overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow><TableHead>Penerima</TableHead><TableHead>Telepon</TableHead><TableHead className="text-right">Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {(detail.recipients || []).map((r) => (
                    <TableRow key={r.id} data-testid={OMNI.bcRecipientRow}>
                      <TableCell className="font-medium">{r.name || "-"}</TableCell>
                      <TableCell className="text-muted-foreground">{r.phone}</TableCell>
                      <TableCell className="text-right">
                        <StatusPill status={r.status} group="wa_send_status" />
                        {r.error_detail || r.skip_reason ? <p className="text-[11px] text-rose-600">{r.error_code || r.skip_reason}{r.error_detail ? `: ${r.error_detail}` : ""}</p> : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
