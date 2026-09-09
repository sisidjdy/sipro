import React, { useEffect, useState } from "react";
import { Landmark, Wallet, ArrowDownToLine, ArrowUpFromLine, AlertTriangle } from "lucide-react";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { CASHBANK } from "@/constants/testIds";

/** Posisi Kas gabungan: saldo buku tiap rekening/kas + mutasi bulan berjalan (dari GL). */
export default function PositionPanel({ refreshKey }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setErr("");
    api.get("/cash-bank/position").then((r) => setData(r.data.data))
      .catch((e) => setErr(e?.response?.data?.detail || "Gagal memuat posisi kas."));
  }, [refreshKey]);

  if (err) return <ErrorState message={err} />;
  if (!data) return <LoadingCards count={4} />;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid={CASHBANK.positionSummary}>
        <MetricCard label="Total Kas & Bank" value={data.total} format="idr" tone="primary" testId={CASHBANK.positionTotal}
          hint={`${data.accounts.filter((a) => a.is_active).length} rekening/kas aktif${data.inactive_balance ? ` · nonaktif ${formatIDR(data.inactive_balance)} tidak dihitung` : ""}`} />
        <MetricCard label="Saldo Bank" value={data.total_bank} format="idr" tone="sky" />
        <MetricCard label="Saldo Kas Tunai" value={data.total_cash} format="idr" tone={data.total_cash < 0 ? "rose" : "emerald"} />
        <MetricCard label={`Mutasi ${data.month}`} value={data.month_in - data.month_out} format="idr"
          tone="amber" hint={`Masuk ${formatIDR(data.month_in)} · Keluar ${formatIDR(data.month_out)}`} />
      </div>

      {data.negative?.length ? (
        <div data-testid={CASHBANK.negativeAlert}
          className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Saldo buku negatif: {data.negative.join(", ")}</p>
            <p className="text-xs text-rose-800/80">Uang keluar dicatat tanpa dana masuk. Catat <b>tarik tunai</b> /
              <b> pengisian kas kecil</b> lewat tab Transfer Internal, atau koreksi jurnalnya.</p>
          </div>
        </div>
      ) : null}

      <div className="rounded-lg border bg-card shadow-[var(--shadow-card)]">
        <Table data-testid={CASHBANK.positionTable}>
          <TableHeader>
            <TableRow>
              <TableHead>Rekening / Kas</TableHead>
              <TableHead>Akun GL</TableHead>
              <TableHead className="text-right"><ArrowDownToLine className="inline h-3.5 w-3.5 mr-1" />Masuk bln ini</TableHead>
              <TableHead className="text-right"><ArrowUpFromLine className="inline h-3.5 w-3.5 mr-1" />Keluar bln ini</TableHead>
              <TableHead className="text-right">Saldo Buku</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.accounts.map((a) => (
              <TableRow key={a.id} data-testid={`${CASHBANK.positionRow}-${a.id}`}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    {a.kind === "cash" ? <Wallet className="h-4 w-4 text-emerald-600" /> : <Landmark className="h-4 w-4 text-sky-600" />}
                    <div>
                      <p className="font-medium leading-tight">{a.name}</p>
                      <p className="text-xs text-muted-foreground">{a.bank_name} · {a.account_no}</p>
                    </div>
                    {a.is_default ? <Badge variant="outline" className="text-[10px]">default</Badge> : null}
                    {!a.is_active ? <Badge variant="secondary" className="text-[10px]">nonaktif</Badge> : null}
                  </div>
                </TableCell>
                <TableCell className="font-mono text-xs">{a.gl_account_code}</TableCell>
                <TableCell className="text-right tabular-nums text-emerald-700">{formatIDR(a.month_in)}</TableCell>
                <TableCell className="text-right tabular-nums text-rose-700">{formatIDR(a.month_out)}</TableCell>
                <TableCell className={`text-right tabular-nums font-semibold ${a.balance < 0 ? "text-rose-700" : ""}`}>
                  {formatIDR(a.balance)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
