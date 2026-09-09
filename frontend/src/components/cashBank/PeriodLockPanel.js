import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Lock, Unlock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import PeriodLockDialog from "@/components/cashBank/PeriodLockDialog";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LOCKS } from "@/constants/testIds";

/** Tutup periode Kas & Bank per rekening (Fase 85): kunci setelah rekonsiliasi seimbang / opname kas. */
export default function PeriodLockPanel({ onChanged }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await api.get("/cash-bank/locks");
      setData(r.data.data); setErr("");
    } catch (e) { setErr(e?.response?.data?.detail || "Gagal memuat kunci periode."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const unlock = async (row) => {
    const reason = window.prompt(`Alasan membuka kunci ${row.name} s.d. ${row.locked_through} (min. 5 karakter):`);
    if (!reason) return;
    setBusy(row.lock_id);
    try {
      await api.post(`/cash-bank/locks/${row.lock_id}/unlock`, { reason });
      toast.success(`Kunci ${row.name} dibuka.`);
      load(); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuka kunci."); } finally { setBusy(""); }
  };

  if (err) return <ErrorState message={err} />;
  if (!data) return <LoadingCards count={2} />;

  return (
    <div className="space-y-5" data-testid={LOCKS.panel}>
      <p className="text-sm text-muted-foreground">
        Rekening bank dikunci setelah rekonsiliasi bulan itu <b>seimbang/dijelaskan</b>; kas tunai setelah
        <b> opname</b> = saldo buku. Jurnal manual ke periode terkunci ditolak, posting otomatis digeser ke bulan terbuka.
      </p>
      <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
        <Table data-testid={LOCKS.table}>
          <TableHeader>
            <TableRow>
              <TableHead>Rekening / Kas</TableHead>
              <TableHead>Akun GL</TableHead>
              <TableHead className="text-right">Saldo Buku</TableHead>
              <TableHead>Terkunci s.d.</TableHead>
              <TableHead className="text-right">Saldo Penutup Terkunci</TableHead>
              <TableHead className="text-right">Aksi</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.accounts.map((a) => (
              <TableRow key={a.account_id} data-testid={`${LOCKS.row}-${a.account_id}`}>
                <TableCell className="font-medium">{a.name} <span className="text-xs text-muted-foreground">({a.kind === "cash" ? "kas" : "bank"})</span></TableCell>
                <TableCell className="font-mono text-xs">{a.gl_account_code}</TableCell>
                <TableCell className="text-right tabular-nums">{formatIDR(a.balance)}</TableCell>
                <TableCell>{a.locked_through ? <Badge className="bg-emerald-100 text-emerald-800 border-0"><Lock className="h-3 w-3 mr-1" />{a.locked_through}</Badge>
                  : <span className="text-xs text-muted-foreground">belum dikunci</span>}</TableCell>
                <TableCell className="text-right tabular-nums">{a.closing_balance != null ? formatIDR(a.closing_balance) : "—"}</TableCell>
                <TableCell className="text-right">
                  {data.can_lock ? (
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="outline" className="h-8" onClick={() => setDialog(a)} data-testid={`${LOCKS.lockBtn}-${a.account_id}`}>
                        <Lock className="h-4 w-4 mr-1" />Kunci periode
                      </Button>
                      {a.lock_id ? (
                        <Button size="sm" variant="ghost" className="h-8 text-rose-700" disabled={busy === a.lock_id} onClick={() => unlock(a)}
                          data-testid={`${LOCKS.unlockBtn}-${a.account_id}`}><Unlock className="h-4 w-4" /></Button>
                      ) : null}
                    </div>
                  ) : <span className="text-xs text-muted-foreground">supervisor keuangan</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {data.history?.length ? (
        <div className="space-y-2" data-testid={LOCKS.history}>
          <h3 className="section-title">Riwayat kunci</h3>
          <ul className="text-sm space-y-1">
            {data.history.slice(0, 20).map((h) => (
              <li key={h.id} className="flex flex-wrap gap-x-3 text-muted-foreground">
                <span className="font-mono text-xs">{h.period}</span>
                <span className="text-foreground">{h.account_name}</span>
                <span>{h.status === "locked" ? "dikunci" : "dibuka"} · {formatIDR(h.closing_balance)}</span>
                <span className="text-xs">{h.recon_status ? `rekonsiliasi ${h.recon_status}` : `opname ${formatIDR(h.counted_balance || 0)}`}</span>
                <span className="text-xs">{(h.status === "locked" ? h.locked_by : h.unlocked_by)}{h.unlock_reason ? ` — ${h.unlock_reason}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <PeriodLockDialog open={!!dialog} account={dialog} onClose={() => setDialog(null)} onSaved={() => { load(); onChanged?.(); }} />
    </div>
  );
}
