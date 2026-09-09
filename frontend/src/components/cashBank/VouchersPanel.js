import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Printer, ReceiptText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { downloadFile } from "@/utils/fileDownload";
import api from "@/services/apiClient";
import { VOUCHER } from "@/constants/testIds";

const PAGE = 50;

/** Bukti Kas Masuk / Keluar (Fase 87): turunan otomatis setiap jurnal kas/bank, bernomor, cetak PDF. */
export default function VouchersPanel({ refreshKey }) {
  const [rows, setRows] = useState(null);
  const [meta, setMeta] = useState({ total: 0, sum_in: 0, sum_out: 0 });
  const [accounts, setAccounts] = useState([]);
  const [filter, setFilter] = useState({ kind: "", account_id: "", q: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => { api.get("/cash-bank/accounts").then((r) => setAccounts(r.data.data || [])).catch(() => {}); }, []);

  const load = useCallback(async (skip = 0) => {
    try {
      const params = { limit: PAGE, skip, ...(filter.kind ? { kind: filter.kind } : {}),
        ...(filter.account_id ? { account_id: filter.account_id } : {}), ...(filter.q ? { q: filter.q } : {}) };
      const r = await api.get("/cash-bank/vouchers", { params });
      setRows((prev) => (skip ? [...(prev || []), ...r.data.data] : r.data.data));
      setMeta({ total: r.data.total, sum_in: r.data.sum_in, sum_out: r.data.sum_out }); setErr("");
    } catch (e) { setErr(e?.response?.data?.detail || "Gagal memuat bukti kas."); }
  }, [filter]);
  useEffect(() => { const t = setTimeout(() => load(0), 250); return () => clearTimeout(t); }, [load, refreshKey]);

  const print = async (v) => {
    setBusy(v.id);
    try { await downloadFile(`/cash-bank/vouchers/${v.id}/pdf`, { fallbackName: `${v.no}.pdf`, open: true }); }
    catch (e) { toast.error("Gagal membuka PDF bukti kas."); } finally { setBusy(""); }
  };

  if (err) return <ErrorState message={err} />;
  if (!rows) return <LoadingCards count={2} />;

  return (
    <div className="space-y-4" data-testid={VOUCHER.panel}>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={filter.kind || "__all__"} onValueChange={(v) => setFilter((f) => ({ ...f, kind: v === "__all__" ? "" : v }))}>
          <SelectTrigger className="h-9 w-[170px]" data-testid={VOUCHER.filterKind}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">BKM & BKK</SelectItem>
            <SelectItem value="BKM">BKM — Kas Masuk</SelectItem>
            <SelectItem value="BKK">BKK — Kas Keluar</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filter.account_id || "__all__"} onValueChange={(v) => setFilter((f) => ({ ...f, account_id: v === "__all__" ? "" : v }))}>
          <SelectTrigger className="h-9 w-[220px]" data-testid={VOUCHER.filterAccount}><SelectValue placeholder="Semua rekening" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Semua rekening & kas</SelectItem>
            {accounts.map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input value={filter.q} onChange={(e) => setFilter((f) => ({ ...f, q: e.target.value }))} className="h-9 w-[240px]"
          placeholder="Cari nomor bukti / jurnal / keterangan" data-testid={VOUCHER.search} />
        <span className="text-sm text-muted-foreground ml-auto" data-testid={VOUCHER.sum}>
          {meta.total} bukti · masuk {formatIDR(meta.sum_in)} · keluar {formatIDR(meta.sum_out)}
        </span>
      </div>
      {rows.length === 0 ? (
        <EmptyState icon={ReceiptText} title="Belum ada bukti kas" description="BKM/BKK terbit otomatis setiap ada jurnal ke rekening/kas." testId={VOUCHER.empty} />
      ) : (
        <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
          <Table data-testid={VOUCHER.table}>
            <TableHeader>
              <TableRow>
                <TableHead>No Bukti</TableHead>
                <TableHead>Tanggal</TableHead>
                <TableHead>Rekening / Kas</TableHead>
                <TableHead>Keterangan</TableHead>
                <TableHead>Lawan akun</TableHead>
                <TableHead className="text-right">Masuk</TableHead>
                <TableHead className="text-right">Keluar</TableHead>
                <TableHead className="text-right">Cetak</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((v) => (
                <TableRow key={v.id} data-testid={`${VOUCHER.row}-${v.id}`}>
                  <TableCell><Badge className={`${v.kind === "BKM" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"} border-0 font-mono text-[11px]`}>{v.no}</Badge>
                    <p className="font-mono text-[10px] text-muted-foreground">{v.entry_no}</p></TableCell>
                  <TableCell className="text-sm whitespace-nowrap">{v.date}</TableCell>
                  <TableCell className="text-sm">{v.cash_account_name}<p className="font-mono text-[10px] text-muted-foreground">{v.cash_account_code}</p></TableCell>
                  <TableCell className="text-sm max-w-[300px]"><p className="truncate" title={v.memo}>{v.memo}</p><p className="text-[10px] text-muted-foreground">{v.source_type}</p></TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[220px] truncate"
                    title={(v.counter || []).map((c) => `${c.account_code} ${c.account_name || ""}: ${formatIDR(Math.abs(c.amount))}`).join("\n")}>
                    {(v.counter || []).map((c) => c.account_name || c.account_code).join(", ")}</TableCell>
                  <TableCell className="text-right tabular-nums text-emerald-700">{v.kind === "BKM" ? formatIDR(v.amount) : ""}</TableCell>
                  <TableCell className="text-right tabular-nums text-rose-700">{v.kind === "BKK" ? formatIDR(v.amount) : ""}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" className="h-8" disabled={busy === v.id} onClick={() => print(v)} data-testid={`${VOUCHER.pdfBtn}-${v.id}`}>
                      <Printer className="h-4 w-4" /></Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {rows.length < meta.total ? (
        <div className="text-center"><Button variant="outline" size="sm" onClick={() => load(rows.length)} data-testid={VOUCHER.more}>Muat {Math.min(PAGE, meta.total - rows.length)} lagi</Button></div>
      ) : null}
    </div>
  );
}
