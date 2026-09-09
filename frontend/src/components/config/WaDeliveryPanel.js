import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateTimeWIB, formatNumber } from "@/utils/formatters";
import { useReference } from "@/context/ReferenceContext";
import { cn } from "@/lib/utils";
import api from "@/services/apiClient";
import { P97 } from "@/constants/testIds";

const CARDS = [
  { key: "total", label: "Semua pesan keluar", tone: "text-foreground" },
  { key: "sent", label: "Terkirim (Meta)", tone: "text-sky-700" },
  { key: "delivered", label: "Sampai", tone: "text-emerald-700" },
  { key: "read", label: "Dibaca", tone: "text-indigo-700" },
  { key: "failed", label: "Gagal", tone: "text-rose-700" },
  { key: "simulated", label: "Simulasi", tone: "text-zinc-600" },
];
const DAYS = [7, 14, 30];

function DrillDialog({ target, onOpenChange }) {
  const navigate = useNavigate();
  const { labelOf } = useReference();
  const [rows, setRows] = useState(null);
  useEffect(() => {
    if (!target) return;
    setRows(null);
    api.get("/wa/messages", { params: { ...target.params, limit: 200 } }).then((r) => setRows(r.data))
      .catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat rincian."));
  }, [target]);
  return (
    <Dialog open={!!target} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid={P97.deliveryDrill}>
        <DialogHeader>
          <DialogTitle>{target?.label}</DialogTitle>
          <DialogDescription>{rows ? `${rows.total} pesan penyusun angka ini` : "Memuat…"}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Waktu</TableHead><TableHead>Penerima</TableHead><TableHead>Jenis</TableHead><TableHead>Isi</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
            <TableBody>
              {(rows?.data || []).map((m) => (
                <TableRow key={m.id} data-testid={P97.deliveryDrillRow} className={cn(m.lead_id && "cursor-pointer")}
                  onClick={() => { if (m.lead_id) { onOpenChange(false); navigate(`/leads/${m.lead_id}`); } }}>
                  <TableCell className="whitespace-nowrap text-xs">{formatDateTimeWIB(m.created_at)}</TableCell>
                  <TableCell className="text-xs">{m.contact_name || "—"}<br /><span className="text-muted-foreground">{m.to}</span></TableCell>
                  <TableCell className="text-xs">{labelOf("wa_message_kind", m.kind)}</TableCell>
                  <TableCell className="max-w-[260px] truncate text-xs" title={m.body}>{m.body}</TableCell>
                  <TableCell className="text-xs">
                    <StatusPill status={m.status} group="wa_send_status" />
                    {m.error_detail ? <p className="mt-0.5 text-[11px] text-rose-600">{m.error_code}: {m.error_detail}</p> : null}
                    {m.lead_id ? <ArrowUpRight className="ml-1 inline h-3 w-3 text-muted-foreground" /> : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Dashboard pengiriman WhatsApp (Fase 98B): kartu = jumlah baris rinciannya (klik untuk membuka). */
export default function WaDeliveryPanel() {
  const { labelOf } = useReference();
  const [days, setDays] = useState(14);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [drill, setDrill] = useState(null);
  const load = useCallback(() => {
    setError("");
    api.get("/wa/stats", { params: { days } }).then((r) => setData(r.data.data))
      .catch((e) => setError(e?.response?.data?.detail || "Gagal memuat statistik pengiriman."));
  }, [days]);
  useEffect(() => { load(); }, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingCards count={3} />;
  const open = (label, params) => setDrill({ label, params: { days, ...params } });
  const maxDay = Math.max(1, ...data.series.map((d) => d.total));

  return (
    <div className="space-y-4" data-testid={P97.deliveryPanel}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Pesan keluar {days} hari terakhir — semua jenis (inbox, broadcast, pengingat, dokumen, OTP). Klik angka untuk melihat pesannya.</p>
        <div className="flex gap-1" data-testid={P97.deliveryDays}>
          {DAYS.map((d) => <Button key={d} size="sm" variant={d === days ? "default" : "outline"} onClick={() => setDays(d)}>{d} hari</Button>)}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {CARDS.map((c) => (
          <button key={c.key} type="button" data-testid={`${P97.deliveryCard}-${c.key}`}
            onClick={() => open(c.label, c.key === "total" ? {} : { status: c.key })}
            className="rounded-xl border bg-card p-3 text-left shadow-[var(--shadow-card)] transition-colors hover:bg-secondary">
            <p className="text-xs text-muted-foreground">{c.label}</p>
            <p className={cn("mt-1 text-2xl font-semibold tabular-nums", c.tone)}>{formatNumber(data.totals[c.key] || 0)}</p>
          </button>
        ))}
      </div>
      <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Per hari</p>
        <div className="flex h-28 items-end gap-1">
          {data.series.map((d) => (
            <button key={d.date} type="button" title={`${d.date}: ${d.total} pesan, ${d.failed} gagal`}
              onClick={() => open(`Pesan ${d.date}`, { day: d.date })}
              className="group flex h-full flex-1 flex-col justify-end gap-px">
              <span className="w-full rounded-t bg-rose-400" style={{ height: `${(d.failed / maxDay) * 100}%` }} />
              <span className="w-full rounded-t bg-primary/70 group-hover:bg-primary" style={{ height: `${((d.total - d.failed) / maxDay) * 100}%` }} />
            </button>
          ))}
        </div>
        <p className="mt-1 flex justify-between text-[10px] text-muted-foreground"><span>{data.series[0]?.date}</span><span>{data.series[data.series.length - 1]?.date}</span></p>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow><TableHead>Jenis</TableHead><TableHead className="text-right">Total</TableHead><TableHead className="text-right">Sampai/Dibaca</TableHead><TableHead className="text-right">Gagal</TableHead><TableHead className="text-right">Simulasi</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.by_kind.map((k) => (
                <TableRow key={k.kind} data-testid={P97.deliveryKindRow} className="cursor-pointer" onClick={() => open(labelOf("wa_message_kind", k.kind), { kind: k.kind })}>
                  <TableCell className="font-medium">{labelOf("wa_message_kind", k.kind)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(k.total)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(k.delivered)}/{formatNumber(k.read)}</TableCell>
                  <TableCell className="text-right tabular-nums text-rose-700">{formatNumber(k.failed)}</TableCell>
                  <TableCell className="text-right tabular-nums text-zinc-600">{formatNumber(k.simulated)}</TableCell>
                </TableRow>
              ))}
              {!data.by_kind.length ? <TableRow><TableCell colSpan={5} className="text-center text-xs text-muted-foreground">Belum ada pesan keluar.</TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </div>
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow><TableHead>Kode gagal</TableHead><TableHead>Alasan</TableHead><TableHead className="text-right">Jumlah</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.failures.map((f) => (
                <TableRow key={f.code} data-testid={P97.deliveryFailureRow} className="cursor-pointer" onClick={() => open(`Gagal ${f.code}`, { status: "failed", code: f.code })}>
                  <TableCell className="font-mono text-xs">{f.code}</TableCell>
                  <TableCell className="max-w-[260px] truncate text-xs" title={f.detail}>{f.detail}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(f.count)}</TableCell>
                </TableRow>
              ))}
              {!data.failures.length ? <TableRow><TableCell colSpan={3} className="text-center text-xs text-muted-foreground">Tidak ada kegagalan pada periode ini.</TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </div>
      </div>
      <DrillDialog target={drill} onOpenChange={(v) => !v && setDrill(null)} />
    </div>
  );
}
