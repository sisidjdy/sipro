import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Landmark, Wallet, Plus, Pencil, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AccountDialog from "@/components/cashBank/AccountDialog";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { CASHBANK } from "@/constants/testIds";

/** Master Kas & Bank terpadu: rekening bank + kas/kas kecil, sub-akun GL, default per jenis. */
export default function AccountsPanel({ onChanged }) {
  const [state, setState] = useState({ rows: null, canManage: false, err: "" });
  const [dialog, setDialog] = useState({ open: false, account: null });

  const load = useCallback(async () => {
    try {
      const r = await api.get("/cash-bank/accounts");
      setState({ rows: r.data.data, canManage: r.data.can_manage, err: "" });
    } catch (e) {
      setState({ rows: [], canManage: false, err: e?.response?.data?.detail || "Gagal memuat rekening." });
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const setDefault = async (row) => {
    try {
      await api.post(`/cash-bank/accounts/${row.id}/set-default`);
      toast.success(`${row.name} kini default untuk ${row.kind === "cash" ? "kas" : "bank"}.`);
      load(); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
  };

  if (state.err) return <ErrorState message={state.err} />;
  if (!state.rows) return <LoadingCards count={2} />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Rekening default dipakai otomatis bila transaksi tidak menyebut rekening. Akun induk 1-1100/1-1200 tidak lagi menerima posting langsung.</p>
        {state.canManage ? (
          <Button size="sm" onClick={() => setDialog({ open: true, account: null })} data-testid={CASHBANK.accountNewBtn}>
            <Plus className="h-4 w-4 mr-1" />Rekening / Kas Baru
          </Button>
        ) : null}
      </div>
      <div className="rounded-lg border bg-card shadow-[var(--shadow-card)] overflow-x-auto">
        <Table data-testid={CASHBANK.accountTable}>
          <TableHeader>
            <TableRow>
              <TableHead>Nama</TableHead>
              <TableHead>Jenis</TableHead>
              <TableHead>No. Rekening / Kode</TableHead>
              <TableHead>Sub-akun GL</TableHead>
              <TableHead className="text-right">Saldo Awal</TableHead>
              <TableHead className="text-right">Saldo Buku</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Aksi</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {state.rows.map((a) => (
              <TableRow key={a.id} data-testid={`${CASHBANK.accountRow}-${a.id}`}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    {a.kind === "cash" ? <Wallet className="h-4 w-4 text-emerald-600" /> : <Landmark className="h-4 w-4 text-sky-600" />}
                    <div>
                      <p className="font-medium leading-tight">{a.name}</p>
                      <p className="text-xs text-muted-foreground">{a.bank_name}{a.holder ? ` · a.n. ${a.holder}` : ""}</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-sm">{a.kind === "cash" ? "Kas" : "Bank"}</TableCell>
                <TableCell className="font-mono text-xs">{a.account_no}</TableCell>
                <TableCell className="font-mono text-xs">{a.gl_account_code}<p className="font-sans text-[11px] text-muted-foreground">{a.gl_account_name}</p></TableCell>
                <TableCell className="text-right tabular-nums text-sm">{formatIDR(a.opening_balance || 0)}
                  {a.opening_posted ? <p className="text-[10px] text-emerald-700">dijurnal</p> : null}</TableCell>
                <TableCell className={`text-right tabular-nums font-semibold ${a.balance < 0 ? "text-rose-700" : ""}`}>{formatIDR(a.balance)}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {a.is_default ? <Badge className="bg-primary/10 text-primary border-0"><Star className="h-3 w-3 mr-1" />default</Badge> : null}
                    <Badge variant={a.is_active ? "outline" : "secondary"}>{a.is_active ? "aktif" : "nonaktif"}</Badge>
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  {state.canManage ? (
                    <div className="flex justify-end gap-1">
                      {!a.is_default && a.is_active ? (
                        <Button size="sm" variant="ghost" className="h-8" onClick={() => setDefault(a)} data-testid={`${CASHBANK.accountSetDefault}-${a.id}`}>
                          <Star className="h-4 w-4" />
                        </Button>
                      ) : null}
                      <Button size="sm" variant="outline" className="h-8" onClick={() => setDialog({ open: true, account: a })} data-testid={`${CASHBANK.accountEdit}-${a.id}`}>
                        <Pencil className="h-3.5 w-3.5 mr-1" />Ubah
                      </Button>
                    </div>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <AccountDialog open={dialog.open} account={dialog.account} onClose={() => setDialog({ open: false, account: null })}
        onSaved={() => { load(); onChanged?.(); }} />
    </div>
  );
}
