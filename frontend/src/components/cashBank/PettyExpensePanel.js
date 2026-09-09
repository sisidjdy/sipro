import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Receipt, Ban, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import RefLabel from "@/components/patterns/RefLabel";
import ImprestCards from "@/components/cashBank/ImprestCards";
import PettyExpenseDialog from "@/components/cashBank/PettyExpenseDialog";
import { formatIDR } from "@/utils/formatters";
import { fileUrl } from "@/utils/photoSrc";
import api from "@/services/apiClient";
import { PETTYX } from "@/constants/testIds";

/** Kas Kecil (Fase 84): keadaan imprest per kas + daftar pengeluaran langsung berbukti. */
export default function PettyExpensePanel({ onChanged }) {
  const [imprest, setImprest] = useState(null);
  const [list, setList] = useState(null);
  const [filter, setFilter] = useState({ account_id: "", status: "" });
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const params = { ...(filter.account_id ? { account_id: filter.account_id } : {}), ...(filter.status ? { status: filter.status } : {}) };
      const [a, b] = await Promise.all([api.get("/petty-cash/imprest"), api.get("/petty-cash/expenses", { params })]);
      setImprest(a.data.data); setList(b.data); setErr("");
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal memuat kas kecil.");
    }
  }, [filter]);
  useEffect(() => { load(); }, [load]);
  const refresh = () => { load(); onChanged?.(); };

  const voidRow = async (r) => {
    const reason = window.prompt(`Alasan pembatalan ${r.no} (min. 5 karakter):`);
    if (!reason) return;
    setBusy(r.id);
    try {
      const res = await api.post(`/petty-cash/expenses/${r.id}/void`, { reason });
      toast.success(`${r.no} dibatalkan → jurnal balik ${res.data.data.void_journal_no}.`);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membatalkan.");
    } finally { setBusy(""); }
  };

  if (err) return <ErrorState message={err} />;
  if (!imprest || !list) return <LoadingCards count={3} />;

  return (
    <div className="space-y-6" data-testid={PETTYX.panel}>
      <ImprestCards data={imprest} onChanged={refresh} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={filter.account_id || "__all__"} onValueChange={(v) => setFilter((f) => ({ ...f, account_id: v === "__all__" ? "" : v }))}>
            <SelectTrigger className="h-9 w-[220px]" data-testid={PETTYX.filterAccount}><SelectValue placeholder="Semua kas" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Semua kas kecil</SelectItem>
              {imprest.accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filter.status || "__all__"} onValueChange={(v) => setFilter((f) => ({ ...f, status: v === "__all__" ? "" : v }))}>
            <SelectTrigger className="h-9 w-[160px]" data-testid={PETTYX.filterStatus}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Semua status</SelectItem>
              <SelectItem value="posted">Tercatat</SelectItem>
              <SelectItem value="voided">Dibatalkan</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-sm text-muted-foreground" data-testid={PETTYX.sum}>
            {list.total} pengeluaran · tercatat {formatIDR(list.sum_posted)}
          </span>
        </div>
        {list.can_create ? (
          <Button size="sm" onClick={() => setOpen(true)} data-testid={PETTYX.newBtn}>
            <Receipt className="h-4 w-4 mr-1" />Catat Pengeluaran
          </Button>
        ) : null}
      </div>
      {list.data.length === 0 ? (
        <EmptyState icon={Receipt} title="Belum ada pengeluaran kas kecil" description="Catat pengeluaran tunai kecil berbukti; jurnal beban dibuat otomatis." testId={PETTYX.empty} />
      ) : (
        <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
          <Table data-testid={PETTYX.table}>
            <TableHeader>
              <TableRow>
                <TableHead>No</TableHead>
                <TableHead>Tanggal</TableHead>
                <TableHead>Kas</TableHead>
                <TableHead>Kategori</TableHead>
                <TableHead>Keterangan</TableHead>
                <TableHead className="text-right">Nominal</TableHead>
                <TableHead>Bukti</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data.map((r) => (
                <TableRow key={r.id} data-testid={`${PETTYX.row}-${r.id}`} className={r.status === "voided" ? "opacity-60" : ""}>
                  <TableCell className="font-mono text-xs">{r.no}</TableCell>
                  <TableCell className="text-sm whitespace-nowrap">{r.date}</TableCell>
                  <TableCell className="text-sm">{r.cash_account_name}</TableCell>
                  <TableCell className="text-sm"><RefLabel group="cashbon_category" value={r.category} /><p className="font-mono text-[10px] text-muted-foreground">{r.expense_account_code}</p></TableCell>
                  <TableCell className="text-sm max-w-[260px]"><p className="truncate">{r.description}</p>
                    {r.payee ? <p className="text-xs text-muted-foreground truncate">→ {r.payee}</p> : null}
                    {r.project_name ? <p className="text-xs text-muted-foreground truncate">{r.project_name}</p> : null}</TableCell>
                  <TableCell className="text-right tabular-nums font-medium">{formatIDR(r.amount)}</TableCell>
                  <TableCell>
                    {(r.file_ids || []).length ? (
                      <div className="flex gap-1">
                        {r.file_ids.map((fid, i) => (
                          <a key={fid} href={fileUrl(fid)} target="_blank" rel="noreferrer" className="text-primary inline-flex items-center text-xs" title={`Bukti ${i + 1}`}>
                            <Paperclip className="h-3.5 w-3.5" />{i + 1}
                          </a>
                        ))}
                      </div>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <Badge className={`${r.status === "posted" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"} border-0`}>
                      {r.status === "posted" ? "Tercatat" : "Dibatalkan"}
                    </Badge>
                    <p className="font-mono text-[10px] text-muted-foreground">{r.status === "voided" ? r.void_journal_no : r.journal_no}</p>
                    {r.status === "voided" && r.void_reason ? <p className="text-[11px] text-rose-700 max-w-[180px]">{r.void_reason}</p> : null}
                  </TableCell>
                  <TableCell className="text-right">
                    {r.status === "posted" && list.can_void ? (
                      <Button size="sm" variant="ghost" className="h-8 text-rose-700" disabled={!!busy} onClick={() => voidRow(r)}
                        data-testid={`${PETTYX.voidBtn}-${r.id}`}><Ban className="h-4 w-4 mr-1" />Batalkan</Button>
                    ) : <span className="text-xs text-muted-foreground">{r.creator_name || r.created_by}</span>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <PettyExpenseDialog open={open} policy={imprest.policy} onClose={() => setOpen(false)} onSaved={refresh} />
    </div>
  );
}
