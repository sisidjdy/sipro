import React, { useCallback, useEffect, useState } from "react";
import { BookOpen } from "lucide-react";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

export default function LedgerPanel() {
  const [accounts, setAccounts] = useState([]);
  const [code, setCode] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/gl/accounts").then((r) => {
      const rows = r.data.data || []; setAccounts(rows);
      const firstWithData = rows.find((a) => a.debit || a.credit) || rows[0];
      if (firstWithData) setCode(firstWithData.code);
    }).catch(() => setAccounts([]));
  }, []);

  const load = useCallback(async () => {
    if (!code) return;
    setLoading(true); setError("");
    try { const r = await api.get("/gl/ledger", { params: { account_code: code } }); setData(r.data.data); }
    catch (e) { setError(e?.response?.data?.detail || "Gagal memuat buku besar."); }
    finally { setLoading(false); }
  }, [code]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <Select value={code} onValueChange={setCode}>
        <SelectTrigger data-testid={GL.ledgerAccountSelect} className="w-full sm:w-96"><SelectValue placeholder="Pilih akun…" /></SelectTrigger>
        <SelectContent>{accounts.map((a) => <SelectItem key={a.code} value={a.code}>{a.code} — {a.name}</SelectItem>)}</SelectContent>
      </Select>
      {loading ? <LoadingCards count={3} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data ? (
          <EmptyState icon={BookOpen} title="Pilih akun" description="Pilih akun untuk melihat mutasi buku besar." />
        ) : !data.lines?.length ? (
          <EmptyState icon={BookOpen} title="Belum ada mutasi" description={`Akun ${data.account?.name || ""} belum memiliki jurnal.`} />
        ) : (
          <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <div className="flex items-center justify-between border-b p-3 text-sm">
              <span className="font-semibold">{data.account?.code} — {data.account?.name}</span>
              <span>Saldo akhir: <b className="tabular-nums">{formatIDR(data.balance)}</b></span>
            </div>
            <Table>
              <TableHeader><TableRow>
                <TableHead>Tanggal</TableHead><TableHead>No. Jurnal</TableHead><TableHead>Keterangan</TableHead>
                <TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Kredit</TableHead><TableHead className="text-right">Saldo</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.lines.map((ln, i) => (
                  <TableRow key={i} data-testid={GL.ledgerRow}>
                    <TableCell className="text-sm">{formatDateWIB(ln.date)}</TableCell>
                    <TableCell className="tabular-nums text-sm">{ln.entry_no}</TableCell>
                    <TableCell className="text-sm">{ln.memo}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{ln.debit ? formatIDR(ln.debit) : "-"}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{ln.credit ? formatIDR(ln.credit) : "-"}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{formatIDR(ln.balance)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
    </div>
  );
}
