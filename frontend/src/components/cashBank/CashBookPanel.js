import React, { useCallback, useEffect, useState } from "react";
import { Download, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState } from "@/components/patterns/StateViews";
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { CASHBANK } from "@/constants/testIds";

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => today().slice(0, 7) + "-01";

/** Buku Kas & Bank: mutasi satu rekening dengan saldo berjalan + ekspor CSV. */
export default function CashBookPanel({ refreshKey }) {
  const [accountId, setAccountId] = useState("");
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!accountId) return;
    setLoading(true); setErr("");
    try {
      const r = await api.get("/cash-bank/book", { params: { account_id: accountId, date_from: from, date_to: to } });
      setData(r.data.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal memuat buku kas/bank.");
    } finally { setLoading(false); }
  }, [accountId, from, to]);

  useEffect(() => { load(); }, [accountId, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const downloadCsv = async () => {
    const r = await api.get("/cash-bank/book", {
      params: { account_id: accountId, date_from: from, date_to: to, format: "csv" }, responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url; a.download = `buku-${data?.account?.account_no || "kas"}-${from}-${to}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-[1fr_160px_160px_auto_auto] md:items-end">
        <CashAccountSelect value={accountId} onChange={setAccountId} label="Rekening / Kas" testId={CASHBANK.bookAccount} />
        <div className="space-y-1.5">
          <Label className="text-xs">Dari</Label>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} data-testid={CASHBANK.bookFrom} className="h-9" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Sampai</Label>
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} data-testid={CASHBANK.bookTo} className="h-9" />
        </div>
        <Button size="sm" onClick={load} disabled={!accountId || loading} data-testid={CASHBANK.bookLoad}>
          <Search className="h-4 w-4 mr-1" />Tampilkan
        </Button>
        <Button size="sm" variant="outline" onClick={downloadCsv} disabled={!data} data-testid={CASHBANK.bookCsv}>
          <Download className="h-4 w-4 mr-1" />CSV
        </Button>
      </div>

      {err ? <ErrorState message={err} /> : null}

      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-4 text-sm">
            <Stat label="Saldo awal" value={data.opening} testId={CASHBANK.bookOpening} />
            <Stat label="Total masuk" value={data.total_in} tone="text-emerald-700" />
            <Stat label="Total keluar" value={data.total_out} tone="text-rose-700" />
            <Stat label="Saldo akhir" value={data.closing} testId={CASHBANK.bookClosing} strong />
          </div>
          {data.lines.length === 0 ? (
            <EmptyState title="Tidak ada mutasi" description="Tidak ada transaksi di rentang tanggal ini." testId={CASHBANK.bookEmpty} />
          ) : (
            <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
              <Table data-testid={CASHBANK.bookTable}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tanggal</TableHead>
                    <TableHead>No Jurnal</TableHead>
                    <TableHead>Keterangan</TableHead>
                    <TableHead>Lawan Akun</TableHead>
                    <TableHead className="text-right">Masuk</TableHead>
                    <TableHead className="text-right">Keluar</TableHead>
                    <TableHead className="text-right">Saldo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.lines.map((ln, i) => (
                    <TableRow key={`${ln.journal_id}-${i}`} data-testid={`${CASHBANK.bookRow}-${i}`}>
                      <TableCell className="whitespace-nowrap">{ln.date}</TableCell>
                      <TableCell className="font-mono text-xs">{ln.entry_no}</TableCell>
                      <TableCell className="max-w-[360px] truncate" title={ln.memo}>{ln.memo}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[220px] truncate" title={ln.counter}>{ln.counter}</TableCell>
                      <TableCell className="text-right tabular-nums text-emerald-700">{ln.in ? formatIDR(ln.in) : ""}</TableCell>
                      <TableCell className="text-right tabular-nums text-rose-700">{ln.out ? formatIDR(ln.out) : ""}</TableCell>
                      <TableCell className={`text-right tabular-nums font-medium ${ln.balance < 0 ? "text-rose-700" : ""}`}>{formatIDR(ln.balance)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value, tone = "", strong = false, testId }) {
  return (
    <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] px-4 py-3" data-testid={testId}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`tabular-nums ${strong ? "font-semibold text-base" : ""} ${tone} ${value < 0 ? "text-rose-700" : ""}`}>{formatIDR(value)}</p>
    </div>
  );
}
