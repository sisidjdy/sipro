import React from "react";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatIDR } from "@/utils/formatters";
import { BANK } from "@/constants/testIds";

export const RECON_STATUS = {
  seimbang: { label: "Seimbang", cls: "bg-emerald-100 text-emerald-800" },
  dijelaskan: { label: "Selisih dijelaskan", cls: "bg-sky-100 text-sky-800" },
  belum_dijelaskan: { label: "Belum dijelaskan", cls: "bg-rose-100 text-rose-800" },
  tanpa_data: { label: "Belum ada mutasi", cls: "bg-muted text-muted-foreground" },
};

export function ReconStatusBadge({ status, testId }) {
  const s = RECON_STATUS[status] || RECON_STATUS.tanpa_data;
  return <Badge data-testid={testId} className={`${s.cls} border-0`}>{s.label}</Badge>;
}

/** Ikhtisar rekonsiliasi SEMUA rekening bank: tiap baris dibanding sub-akun GL-nya sendiri. */
export default function ReconOverviewTable({ rows, selectedId, onSelect }) {
  if (!rows) return null;
  return (
    <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
      <Table data-testid={BANK.overviewTable}>
        <TableHeader>
          <TableRow>
            <TableHead>Rekening</TableHead>
            <TableHead>Sub-akun GL</TableHead>
            <TableHead>Per tanggal</TableHead>
            <TableHead className="text-right">Saldo rekening</TableHead>
            <TableHead className="text-right">Saldo buku</TableHead>
            <TableHead className="text-right">Residu</TableHead>
            <TableHead className="text-center">Belum cocok / tanpa alasan</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.account_id} data-testid={`${BANK.overviewRow}-${r.account_id}`}
              onClick={() => onSelect?.(r.account_id)}
              className={`cursor-pointer ${selectedId === r.account_id ? "bg-primary/5" : ""}`}>
              <TableCell>
                <p className="font-medium leading-tight">{r.name}</p>
                <p className="text-xs text-muted-foreground">{r.bank_name} · {r.account_no}{!r.is_active ? " · nonaktif" : ""}</p>
              </TableCell>
              <TableCell className="font-mono text-xs">{r.gl_account_code}</TableCell>
              <TableCell className="text-sm">{r.statement_balance === null ? "—" : r.as_of}</TableCell>
              <TableCell className="text-right tabular-nums">{r.statement_balance === null ? <span className="text-muted-foreground">belum ada</span> : formatIDR(r.statement_balance)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatIDR(r.book_balance)}</TableCell>
              <TableCell className={`text-right tabular-nums font-medium ${r.residual ? "text-rose-700" : ""}`}>
                {r.residual === null ? "—" : formatIDR(r.residual)}
              </TableCell>
              <TableCell className="text-center text-sm tabular-nums">{r.unmatched_count} / {r.unexplained_count}</TableCell>
              <TableCell><ReconStatusBadge status={r.status} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
