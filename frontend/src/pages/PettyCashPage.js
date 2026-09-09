import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Wallet, Plus, Check, X, HandCoins, ClipboardList, Ban } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import MetricCard from "@/components/patterns/MetricCard";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import RequestAdvanceDialog from "@/components/pettyCash/RequestAdvanceDialog";
import DisburseAdvanceDialog from "@/components/pettyCash/DisburseAdvanceDialog";
import SettleAdvanceDialog from "@/components/pettyCash/SettleAdvanceDialog";
import AdvanceDetailSheet from "@/components/pettyCash/AdvanceDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PETTY } from "@/constants/testIds";

/**
 * Kas Bon (petty cash / uang muka karyawan) — Fase 27.
 *
 * Uang yang dipegang staf untuk kebutuhan lapangan BUKAN beban sampai
 * dipertanggungjawabkan: pencairan mencatat piutang karyawan (akun 1-1500),
 * pertanggungjawaban memindahkannya ke beban/WIP dan mengembalikan sisanya.
 */
export default function PettyCashPage() {
  const { user } = useAuth();
  const { labelOf } = useReference();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [canApprove, setCanApprove] = useState(false);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openRequest, setOpenRequest] = useState(false);
  const [disburse, setDisburse] = useState(null);
  const [settle, setSettle] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [list, sum] = await Promise.all([
        api.get("/petty-cash/advances", { params: status ? { status } : {} }),
        api.get("/petty-cash/summary"),
      ]);
      setRows(list.data.data || []);
      setCanApprove(Boolean(list.data.can_approve));
      setSummary(sum.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data kas bon.");
    } finally { setLoading(false); }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const act = async (row, action) => {
    setBusy(row.id);
    try {
      // Path ditulis eksplisit per aksi (bukan template dinamis) agar kontrak
      // FE<->BE bisa diverifikasi otomatis oleh gate verify_api_contract.
      if (action === "approve") {
        await api.post(`/petty-cash/advances/${row.id}/approve`, { note: null });
      } else if (action === "reject") {
        await api.post(`/petty-cash/advances/${row.id}/reject`, { note: null });
      } else {
        await api.post(`/petty-cash/advances/${row.id}/cancel`);
      }
      toast.success(action === "approve" ? `Kas bon ${row.no} disetujui.`
        : action === "reject" ? `Kas bon ${row.no} ditolak.`
          : `Kas bon ${row.no} dibatalkan.`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal diproses.");
    } finally { setBusy(""); }
  };

  const isMine = (row) => row.requested_by === user?.email;
  const statusOptions = useMemo(
    () => ["submitted", "approved", "disbursed", "settled", "rejected", "cancelled"], []);

  return (
    <div data-testid={PETTY.page} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Wallet className="h-5 w-5 text-primary" />
          <div>
            <h1 className="page-title">Kas Bon</h1>
            <p className="text-xs text-muted-foreground">
              Uang muka karyawan (akun 1-1500) — dicairkan, dipakai, lalu dipertanggungjawabkan.
            </p>
          </div>
        </div>
        <Button data-testid={PETTY.requestBtn} onClick={() => setOpenRequest(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Ajukan Kas Bon
        </Button>
      </div>

      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> : (
        <>
          <div data-testid={PETTY.summary} className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="Kas Bon Berjalan" value={summary?.outstanding_amount || 0}
              tone="indigo" format="idr"
              hint={`${summary?.outstanding_count || 0} kas bon belum dipertanggungjawabkan`} />
            <MetricCard label="Menunggu Persetujuan" value={summary?.waiting_approval_amount || 0}
              tone="amber" format="idr" hint={`${summary?.waiting_approval || 0} pengajuan`} />
            <MetricCard label="Siap Dicairkan" value={summary?.ready_to_disburse_amount || 0}
              tone="primary" format="idr" hint={`${summary?.ready_to_disburse || 0} disetujui`} />
            <MetricCard label="Sudah Direalisasi" value={summary?.settled_amount || 0}
              tone="emerald" format="idr" hint="Total beban dari kas bon selesai" />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Filter status</span>
            <Select value={status || "__all__"} onValueChange={(v) => setStatus(v === "__all__" ? "" : v)}>
              <SelectTrigger data-testid={PETTY.filter} className="w-56">
                <SelectValue placeholder="Semua status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua status</SelectItem>
                {statusOptions.map((s) => (
                  <SelectItem key={s} value={s}>{labelOf("cashbon_status", s)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {!rows.length ? (
            <div data-testid={PETTY.empty}>
              <EmptyState icon={Wallet} title="Belum ada kas bon"
                description="Ajukan kas bon untuk kebutuhan lapangan; finance akan menyetujui lalu mencairkannya."
                actionLabel="Ajukan Kas Bon" onAction={() => setOpenRequest(true)} />
            </div>
          ) : (
            <div data-testid={PETTY.table} className="overflow-hidden rounded-xl border bg-card shadow-sm">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>No.</TableHead>
                    <TableHead>Keperluan</TableHead>
                    <TableHead>Pemohon</TableHead>
                    <TableHead>Kategori</TableHead>
                    <TableHead className="text-right">Diajukan</TableHead>
                    <TableHead className="text-right">Dicairkan</TableHead>
                    <TableHead className="text-right">Realisasi</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="col-actions-head text-right">Aksi</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.id} data-testid={PETTY.row} data-status={r.status}>
                      <TableCell className="font-medium">{r.no}</TableCell>
                      <TableCell className="max-w-[260px]">
                        <p className="truncate" title={r.purpose}>{r.purpose}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {r.project_name || "Tanpa proyek"} · {formatDateWIB(r.created_at)}
                        </p>
                      </TableCell>
                      <TableCell className="text-sm">{r.requester_name || r.requested_by}</TableCell>
                      <TableCell className="text-sm">
                        <RefLabel group="cashbon_category" value={r.category} />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{formatIDR(r.amount_requested)}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.disbursed_amount ? formatIDR(r.disbursed_amount) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {r.expense_total ? formatIDR(r.expense_total) : "—"}
                      </TableCell>
                      <TableCell><StatusPill status={r.status} group="cashbon_status" /></TableCell>
                      <TableCell className="col-actions">
                        <div className="flex flex-wrap justify-end gap-1.5">
                          <Button size="sm" variant="ghost" data-testid={PETTY.detailBtn}
                            onClick={() => setDetail(r)}>Detail</Button>
                          {canApprove && r.status === "submitted" ? (
                            <>
                              <Button size="sm" data-testid={PETTY.approveBtn} disabled={busy === r.id}
                                onClick={() => act(r, "approve")}>
                                <Check className="mr-1 h-3.5 w-3.5" /> Setujui
                              </Button>
                              <Button size="sm" variant="outline" data-testid={PETTY.rejectBtn}
                                disabled={busy === r.id} onClick={() => act(r, "reject")}>
                                <X className="mr-1 h-3.5 w-3.5" /> Tolak
                              </Button>
                            </>
                          ) : null}
                          {canApprove && r.status === "approved" ? (
                            <Button size="sm" data-testid={PETTY.disburseBtn}
                              onClick={() => setDisburse(r)}>
                              <HandCoins className="mr-1 h-3.5 w-3.5" /> Cairkan
                            </Button>
                          ) : null}
                          {r.status === "disbursed" && (isMine(r) || canApprove) ? (
                            <Button size="sm" data-testid={PETTY.settleBtn}
                              onClick={() => setSettle(r)}>
                              <ClipboardList className="mr-1 h-3.5 w-3.5" /> Pertanggungjawaban
                            </Button>
                          ) : null}
                          {["submitted", "approved"].includes(r.status) && isMine(r) ? (
                            <Button size="sm" variant="outline" data-testid={PETTY.cancelBtn}
                              disabled={busy === r.id} onClick={() => act(r, "cancel")}>
                              <Ban className="mr-1 h-3.5 w-3.5" /> Batalkan
                            </Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}

      <RequestAdvanceDialog open={openRequest} onOpenChange={setOpenRequest} onSaved={load} />
      <DisburseAdvanceDialog advance={disburse} onClose={() => setDisburse(null)} onSaved={load} />
      <SettleAdvanceDialog advance={settle} onClose={() => setSettle(null)} onSaved={load} />
      <AdvanceDetailSheet advance={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
