import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { FileCheck2, Ban, Undo2, Plus } from "lucide-react";
import MetricCard from "@/components/patterns/MetricCard";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import PdcDialog from "@/components/cashBank/PdcDialog";
import PdcClearDialog from "@/components/cashBank/PdcClearDialog";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PDC } from "@/constants/testIds";

const STATUS = {
  received: { label: "Di tangan", cls: "bg-amber-100 text-amber-800" },
  cleared: { label: "Cair", cls: "bg-emerald-100 text-emerald-800" },
  bounced: { label: "Ditolak bank", cls: "bg-rose-100 text-rose-800" },
  cancelled: { label: "Dibatalkan", cls: "bg-slate-100 text-slate-700" },
};

/** Giro / cek mundur (Fase 86): di tangan → cair ke bank (kwitansi) / ditolak / dibatalkan. */
export default function PdcPanel({ onChanged }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  const [clearing, setClearing] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await api.get("/pdc", { params: status ? { status } : {} });
      setData(r.data); setErr("");
    } catch (e) { setErr(e?.response?.data?.detail || "Gagal memuat giro."); }
  }, [status]);
  useEffect(() => { load(); }, [load]);
  const refresh = () => { load(); onChanged?.(); };

  const act = async (row, action) => {
    const reason = window.prompt(action === "bounce" ? `Alasan tolakan bank untuk ${row.no}:` : `Alasan pembatalan ${row.no}:`);
    if (!reason) return;
    setBusy(row.id + action);
    try {
      if (action === "bounce") await api.post(`/pdc/${row.id}/bounce`, { reason });
      else await api.post(`/pdc/${row.id}/cancel`, { reason });
      toast.success(action === "bounce" ? `${row.no} dicatat ditolak bank.` : `${row.no} dibatalkan.`);
      refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Aksi gagal."); } finally { setBusy(""); }
  };

  if (err) return <ErrorState message={err} />;
  if (!data) return <LoadingCards count={3} />;
  const s = data.summary;

  return (
    <div className="space-y-5" data-testid={PDC.panel}>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid={PDC.summary}>
        <MetricCard label="Giro di tangan" value={s.in_hand_amount} format="idr" tone="amber" hint={`${s.in_hand_count} warkat belum cair`} />
        <MetricCard label="Jatuh tempo ≤ 7 hari" value={s.due_soon_amount} format="idr" tone="sky" hint="Segera setorkan ke bank" />
        <MetricCard label="Lewat jatuh tempo" value={s.overdue_count} tone={s.overdue_count ? "rose" : "emerald"} hint="warkat belum disetor/dikliring" />
        <MetricCard label="Ditolak bank" value={s.bounced_count} tone={s.bounced_count ? "rose" : "emerald"} hint="tagihan tetap terbuka" />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select value={status || "__all__"} onValueChange={(v) => setStatus(v === "__all__" ? "" : v)}>
          <SelectTrigger className="h-9 w-[180px]" data-testid={PDC.filterStatus}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Semua status</SelectItem>
            {Object.entries(STATUS).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
          </SelectContent>
        </Select>
        {data.can_create ? (
          <Button size="sm" onClick={() => setOpen(true)} data-testid={PDC.newBtn}><Plus className="h-4 w-4 mr-1" />Terima Giro</Button>
        ) : null}
      </div>
      {data.data.length === 0 ? (
        <EmptyState icon={FileCheck2} title="Belum ada giro/cek" description="Catat cek atau bilyet giro yang diterima dari pembeli." testId={PDC.empty} />
      ) : (
        <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
          <Table data-testid={PDC.table}>
            <TableHeader>
              <TableRow>
                <TableHead>No</TableHead>
                <TableHead>Warkat</TableHead>
                <TableHead>Dari / Unit</TableHead>
                <TableHead className="text-right">Nominal</TableHead>
                <TableHead>Jatuh tempo</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.data.map((r) => {
                const st = STATUS[r.status] || STATUS.received;
                return (
                  <TableRow key={r.id} data-testid={`${PDC.row}-${r.id}`}>
                    <TableCell className="font-mono text-xs">{r.no}</TableCell>
                    <TableCell className="text-sm">{r.kind_label} {r.instrument_no}<p className="text-xs text-muted-foreground">{r.bank_name}</p></TableCell>
                    <TableCell className="text-sm">{r.issuer_name}{r.unit_code ? <p className="text-xs text-muted-foreground">Unit {r.unit_code}</p> : <p className="text-xs text-muted-foreground">tanpa deal</p>}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{formatIDR(r.amount)}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">{r.due_date}
                      {r.overdue ? <p className="text-[11px] text-rose-700">lewat jatuh tempo</p> : r.due_soon ? <p className="text-[11px] text-amber-700">≤ 7 hari</p> : null}</TableCell>
                    <TableCell>
                      <Badge className={`${st.cls} border-0`}>{st.label}</Badge>
                      {r.status === "cleared" ? <p className="text-[10px] text-muted-foreground">{r.cash_account_name}{r.receipt_no ? ` · ${r.receipt_no}` : ""}</p> : null}
                      {r.status === "bounced" && r.bounce_reason ? <p className="text-[11px] text-rose-700 max-w-[180px]">{r.bounce_reason}</p> : null}
                    </TableCell>
                    <TableCell className="text-right">
                      {r.status === "received" && data.can_update ? (
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="outline" className="h-8" disabled={!!busy} onClick={() => setClearing(r)} data-testid={`${PDC.clearBtn}-${r.id}`}>
                            <FileCheck2 className="h-4 w-4 mr-1" />Cairkan</Button>
                          <Button size="sm" variant="ghost" className="h-8 text-rose-700" disabled={!!busy} onClick={() => act(r, "bounce")} data-testid={`${PDC.bounceBtn}-${r.id}`} title="Ditolak bank"><Ban className="h-4 w-4" /></Button>
                          <Button size="sm" variant="ghost" className="h-8" disabled={!!busy} onClick={() => act(r, "cancel")} data-testid={`${PDC.cancelBtn}-${r.id}`} title="Batalkan / kembalikan"><Undo2 className="h-4 w-4" /></Button>
                        </div>
                      ) : <span className="text-xs text-muted-foreground">{r.received_by}</span>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <PdcDialog open={open} kinds={data.kinds} onClose={() => setOpen(false)} onSaved={refresh} />
      <PdcClearDialog open={!!clearing} pdc={clearing} onClose={() => setClearing(null)} onSaved={refresh} />
    </div>
  );
}
