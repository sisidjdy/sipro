import React, { useCallback, useEffect, useState } from "react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { BookOpen } from "lucide-react";
import { GL } from "@/constants/testIds";

/**
 * Drill-down: dari baris laporan (Laba Rugi / Neraca / Neraca Lajur) langsung ke
 * mutasi buku besar akun tersebut pada periode yang sama, lalu ke jurnal aslinya.
 */
export default function LedgerDrillSheet({ accountCode, period, open, onOpenChange }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [journal, setJournal] = useState(null);

  const load = useCallback(async () => {
    if (!accountCode || !open) return;
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/reports/ledger", {
        params: { account_code: accountCode, date_from: period?.date_from, date_to: period?.date_to },
      });
      setData(r.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat mutasi buku besar.");
    } finally { setLoading(false); }
  }, [accountCode, open, period?.date_from, period?.date_to]);

  useEffect(() => { load(); }, [load]);

  const openJournal = async (id) => {
    try {
      const r = await api.get(`/gl/journals/${id}`);
      setJournal(r.data.data);
    } catch { setJournal(null); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={GL.drillSheet} data-account-code={accountCode}
        className="w-full overflow-y-auto sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle className="font-heading text-lg">
            {data?.account ? `${data.account.code} — ${data.account.name}` : "Buku Besar"}
          </SheetTitle>
          <SheetDescription>
            Mutasi {period?.date_from} s/d {period?.date_to} · klik baris untuk melihat jurnal asal
          </SheetDescription>
        </SheetHeader>

        {loading ? <div className="mt-4"><LoadingCards count={3} /></div> :
          error ? <div className="mt-4"><ErrorState message={error} onRetry={load} /></div> :
            !data?.lines?.length ? (
              <div className="mt-4">
                <EmptyState icon={BookOpen} title="Tidak ada mutasi pada periode ini"
                  description="Ubah periode atau pilih akun lain untuk melihat mutasinya." />
              </div>
            ) : (
              <>
                <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
                  <div className="rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
                    <p className="text-[11px] text-muted-foreground">Saldo awal</p>
                    <p className="font-semibold tabular-nums">{formatIDR(data.opening)}</p>
                  </div>
                  <div className="rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
                    <p className="text-[11px] text-muted-foreground">Mutasi (D / K)</p>
                    <p className="font-semibold tabular-nums">
                      {formatIDR(data.total_debit)} / {formatIDR(data.total_credit)}
                    </p>
                  </div>
                  <div className="rounded-lg border bg-accent/50 p-2.5">
                    <p className="text-[11px] text-muted-foreground">Saldo akhir</p>
                    <p className="font-semibold tabular-nums text-primary">{formatIDR(data.closing)}</p>
                  </div>
                </div>
                <div className="mt-3 w-full max-w-full overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
                  <Table>
                    <TableHeader><TableRow>
                      <TableHead className="whitespace-nowrap">Tanggal</TableHead><TableHead>No.</TableHead><TableHead>Keterangan</TableHead>
                      <TableHead className="text-right">Debit</TableHead>
                      <TableHead className="text-right">Kredit</TableHead>
                      <TableHead className="text-right">Saldo</TableHead>
                    </TableRow></TableHeader>
                    <TableBody>
                      {data.lines.map((ln, i) => (
                        <TableRow key={`${ln.entry_no}-${i}`} data-testid={GL.drillRow}
                          data-entry-no={ln.entry_no} className="cursor-pointer hover:bg-accent/40"
                          onClick={() => openJournal(ln.journal_id)}>
                          <TableCell className="text-sm">{formatDateWIB(ln.date)}</TableCell>
                          <TableCell className="tabular-nums text-xs">{ln.entry_no}</TableCell>
                          <TableCell className="text-sm">{ln.memo}</TableCell>
                          <TableCell className="text-right tabular-nums text-sm">{ln.debit ? formatIDR(ln.debit) : "-"}</TableCell>
                          <TableCell className="text-right tabular-nums text-sm">{ln.credit ? formatIDR(ln.credit) : "-"}</TableCell>
                          <TableCell className="text-right tabular-nums text-sm font-medium">{formatIDR(ln.balance)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </>
            )}

        <Dialog open={!!journal} onOpenChange={(v) => !v && setJournal(null)}>
          <DialogContent data-testid={GL.drillJournal} className="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>{journal?.entry_no}</DialogTitle>
              <DialogDescription>
                {journal ? `${formatDateWIB(journal.date)} · ${journal.auto ? "Otomatis" : "Manual"} · ${journal.posted_by}` : ""}
              </DialogDescription>
            </DialogHeader>
            <p className="rounded-lg bg-secondary p-3 text-sm">{journal?.memo}</p>
            <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Akun</TableHead>
                  <TableHead className="text-right">Debit</TableHead>
                  <TableHead className="text-right">Kredit</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(journal?.lines || []).map((ln, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-sm">
                        <span className="tabular-nums text-muted-foreground">{ln.account_code}</span> {ln.account_name}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">{ln.debit ? formatIDR(ln.debit) : "-"}</TableCell>
                      <TableCell className="text-right tabular-nums text-sm">{ln.credit ? formatIDR(ln.credit) : "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </DialogContent>
        </Dialog>
      </SheetContent>
    </Sheet>
  );
}
