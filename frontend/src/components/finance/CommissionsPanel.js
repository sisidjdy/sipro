import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BadgePercent, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { FINANCE } from "@/constants/testIds";
import RefLabel from "@/components/patterns/RefLabel";


export default function CommissionsPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/finance/commissions");
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data komisi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const approve = async (row) => {
    setBusyId(row.id);
    try {
      await api.post(`/finance/commissions/${row.id}/approve`, {});
      toast.success(`Komisi ${formatIDR(row.amount)} disetujui.`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyetujui komisi."); }
    finally { setBusyId(null); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const totalPending = rows.filter((r) => r.status === "pending").reduce((s, r) => s + (r.amount || 0), 0);

  return (
    <div data-testid={FINANCE.commissionsPanel} className="space-y-5">
      <div className="rounded-xl border bg-card p-4 shadow-sm">
        <p className="text-xs text-muted-foreground">Total komisi menunggu approval</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-amber-700">{formatIDR(totalPending)}</p>
      </div>

      {!rows.length ? (
        <EmptyState icon={BadgePercent} title="Belum ada komisi"
          description="Komisi dihitung otomatis (skema bertingkat) saat unit di-booking / lunas." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Unit</TableHead>
                <TableHead>Sales</TableHead>
                <TableHead>Skema</TableHead>
                <TableHead className="text-right">Basis</TableHead>
                <TableHead className="text-right">Rate</TableHead>
                <TableHead className="text-right">Komisi</TableHead>
                <TableHead>Trigger</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={FINANCE.commissionRow}>
                  <TableCell className="font-medium">{r.unit_code || "-"}</TableCell>
                  <TableCell>{r.assigned_to || "-"}</TableCell>
                  <TableCell className="text-muted-foreground">{r.scheme_name || "-"}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.base)}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.rate_pct}%</TableCell>
                  <TableCell className="text-right font-semibold tabular-nums text-primary">{formatIDR(r.amount)}</TableCell>
                  <TableCell className="text-muted-foreground"><RefLabel group="commission_trigger" value={r.trigger} /></TableCell>
                  <TableCell><StatusPill status={r.status} group="commission_status" /></TableCell>
                  <TableCell className="col-actions">
                    <div className="flex justify-end">
                      {r.status === "pending" ? (
                        <Button size="sm" variant="outline" data-testid={FINANCE.commissionApproveBtn}
                          onClick={() => approve(r)} disabled={busyId === r.id}>
                          <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Setujui
                        </Button>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">Disetujui</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
