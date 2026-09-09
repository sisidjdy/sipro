import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowLeftRight, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import TransferDialog from "@/components/cashBank/TransferDialog";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { CASHBANK } from "@/constants/testIds";

const STATUS = {
  pending: { label: "Menunggu", cls: "bg-amber-100 text-amber-800" },
  posted: { label: "Diposting", cls: "bg-emerald-100 text-emerald-800" },
  rejected: { label: "Ditolak", cls: "bg-rose-100 text-rose-800" },
};

/** Transfer internal: daftar + ajukan + setujui/tolak (SoD: pembuat ≠ penyetuju). */
export default function TransfersPanel({ onChanged }) {
  const [state, setState] = useState({ rows: null, kinds: [], canApprove: false, canCreate: false, err: "" });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await api.get("/cash-bank/transfers");
      setState({ rows: r.data.data, kinds: r.data.kinds, canApprove: r.data.can_approve,
        canCreate: r.data.can_create, err: "" });
    } catch (e) {
      setState((s) => ({ ...s, rows: [], err: e?.response?.data?.detail || "Gagal memuat transfer." }));
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  const canCreate = state.canCreate;

  const act = async (row, action) => {
    let body = {};
    if (action === "reject") {
      const reason = window.prompt("Alasan penolakan (min. 5 karakter):");
      if (!reason) return;
      body = { reason };
    }
    setBusy(row.id + action);
    try {
      const r = action === "approve"
        ? await api.post(`/cash-bank/transfers/${row.id}/approve`, {})
        : await api.post(`/cash-bank/transfers/${row.id}/reject`, body);
      toast.success(action === "approve" ? `${row.no} diposting → jurnal ${r.data.data.journal_no}.` : `${row.no} ditolak.`);
      await load(); onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal.");
    } finally { setBusy(""); }
  };

  if (state.err) return <ErrorState message={state.err} />;
  if (!state.rows) return <LoadingCards count={2} />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Transfer antar rekening, setor/tarik tunai, dan pengisian kas kecil — dijurnal otomatis setelah disetujui.</p>
        {canCreate ? (
          <Button size="sm" onClick={() => setOpen(true)} data-testid={CASHBANK.transferNewBtn}>
            <ArrowLeftRight className="h-4 w-4 mr-1" />Transaksi Baru
          </Button>
        ) : null}
      </div>
      {state.rows.length === 0 ? (
        <EmptyState icon={ArrowLeftRight} title="Belum ada transaksi internal" description="Ajukan transfer, setor, atau tarik tunai pertama." testId={CASHBANK.transferEmpty} />
      ) : (
        <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
          <Table data-testid={CASHBANK.transferTable}>
            <TableHeader>
              <TableRow>
                <TableHead>No</TableHead>
                <TableHead>Jenis</TableHead>
                <TableHead>Dari → Ke</TableHead>
                <TableHead className="text-right">Nominal</TableHead>
                <TableHead className="text-right">Biaya</TableHead>
                <TableHead>Tanggal</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {state.rows.map((r) => {
                const st = STATUS[r.status] || STATUS.pending;
                return (
                  <TableRow key={r.id} data-testid={`${CASHBANK.transferRow}-${r.id}`}>
                    <TableCell className="font-mono text-xs">{r.no}</TableCell>
                    <TableCell className="text-sm">{r.kind_label}</TableCell>
                    <TableCell className="text-sm">{r.from_name} <span className="text-muted-foreground">→</span> {r.to_name}
                      {r.note ? <p className="text-xs text-muted-foreground truncate max-w-[260px]">{r.note}</p> : null}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{formatIDR(r.amount)}</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">{r.fee ? formatIDR(r.fee) : "—"}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">{r.date}</TableCell>
                    <TableCell>
                      <Badge className={`${st.cls} border-0`}>{st.label}</Badge>
                      {r.journal_no ? <p className="font-mono text-[10px] text-muted-foreground">{r.journal_no}</p> : null}
                      {r.status === "rejected" && r.reject_reason ? <p className="text-[11px] text-rose-700">{r.reject_reason}</p> : null}
                    </TableCell>
                    <TableCell className="text-right">
                      {r.status === "pending" && state.canApprove ? (
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="outline" className="h-8" disabled={!!busy} onClick={() => act(r, "approve")}
                            data-testid={`${CASHBANK.transferApprove}-${r.id}`}><Check className="h-4 w-4 mr-1" />Setujui</Button>
                          <Button size="sm" variant="ghost" className="h-8 text-rose-700" disabled={!!busy} onClick={() => act(r, "reject")}
                            data-testid={`${CASHBANK.transferReject}-${r.id}`}><X className="h-4 w-4" /></Button>
                        </div>
                      ) : <span className="text-xs text-muted-foreground">{r.approved_by || r.created_by}</span>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <TransferDialog open={open} kinds={state.kinds} onClose={() => setOpen(false)} onSaved={() => { load(); onChanged?.(); }} />
    </div>
  );
}
