import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Handshake, Plus, Check, X, Banknote, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import SubmitFeeDialog from "@/components/marketingFee/SubmitFeeDialog";
import PayFeeDialog from "@/components/marketingFee/PayFeeDialog";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { MFEE } from "@/constants/testIds";

/** Pengajuan marketing fee: hitung otomatis, approval finance, pembayaran. */
export default function FeesPanel() {
  // Pemisahan tugas (RBAC `marketing_fee`): sales/marketing MENGAJUKAN, finance
  // MENYETUJUI + MEMBAYAR. Finance tidak punya izin `create`, jadi tombol "Ajukan Fee"
  // dulu adalah CTA MATI untuknya — ditekan, jawabannya 403. Tombolnya kini mengikuti
  // izin efektif dari `GET /auth/me`, sama seperti tombol Setujui/Bayar.
  const { can } = useAuth();
  const canSubmit = can("marketing_fee", "create");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [canApprove, setCanApprove] = useState(false);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openSubmit, setOpenSubmit] = useState(false);
  const [payFee, setPayFee] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [list, sum] = await Promise.all([
        api.get("/marketing/fees", { params: status ? { status } : {} }),
        api.get("/marketing/summary"),
      ]);
      setRows(list.data.data || []);
      setCanApprove(Boolean(list.data.can_approve));
      setSummary(sum.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat pengajuan marketing fee.");
    } finally { setLoading(false); }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const act = async (row, action) => {
    setBusy(row.id);
    try {
      // Path eksplisit per aksi agar gate verify_api_contract dapat memverifikasinya.
      if (action === "approve") {
        await api.post(`/marketing/fees/${row.id}/approve`, { note: null });
      } else {
        await api.post(`/marketing/fees/${row.id}/reject`, { note: null });
      }
      toast.success(action === "approve" ? `Fee ${row.no} disetujui & dibukukan.`
        : `Fee ${row.no} ditolak.`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal diproses.");
    } finally { setBusy(""); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={MFEE.feesPanel} className="space-y-5">
      <div data-testid={MFEE.summary} className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Utang Fee (belum dibayar)" value={summary?.payable_amount || 0}
          tone="rose" format="idr" hint="Akun 2-1500" />
        <MetricCard label="Menunggu Persetujuan" value={summary?.waiting_approval_amount || 0}
          tone="amber" format="idr" hint={`${summary?.waiting_approval || 0} pengajuan`} />
        <MetricCard label="Sudah Dibayar" value={summary?.paid_amount || 0} tone="emerald"
          format="idr" hint="Total dibayarkan ke mitra" />
        <MetricCard label="PPh Dipotong" value={summary?.pph_total || 0} tone="indigo"
          format="idr" hint="Disetorkan lewat menu Perpajakan" />
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-56 space-y-1">
          <span className="text-xs text-muted-foreground">Status pengajuan</span>
          <ReferenceSelect group="marketing_fee_status" value={status} onChange={setStatus}
            allowEmpty emptyLabel="Semua status" testId={MFEE.statusFilter} />
        </div>
        <Button data-testid={MFEE.submitBtn} onClick={() => setOpenSubmit(true)}
          disabled={!canSubmit}
          title={canSubmit ? undefined
            : "Peran Anda menyetujui & membayar fee, bukan mengajukannya "
              + "(pemisahan tugas). Minta sales/marketing yang mengajukan."}>
          <Plus className="mr-1.5 h-4 w-4" /> Ajukan Fee
        </Button>
      </div>

      {!rows.length ? (
        <div data-testid={MFEE.feesEmpty}>
          <EmptyState icon={Handshake} title="Belum ada pengajuan marketing fee"
            description="Ajukan fee untuk agen/broker/referral atas deal tertentu; finance akan menyetujui lalu membayarnya."
            actionLabel={canSubmit ? "Ajukan Fee" : undefined}
            onAction={canSubmit ? () => setOpenSubmit(true) : undefined} />
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No.</TableHead>
                <TableHead>Agen / Mitra</TableHead>
                <TableHead>Unit & Pemicu</TableHead>
                <TableHead>Dasar</TableHead>
                <TableHead className="text-right">Bruto</TableHead>
                <TableHead className="text-right">PPh</TableHead>
                <TableHead className="text-right">Netto</TableHead>
                <TableHead className="text-right">Dibayar</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={MFEE.feeRow} data-status={r.status}>
                  <TableCell className="font-medium">{r.no}</TableCell>
                  <TableCell>
                    <p className="text-sm">{r.agent_name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      <RefLabel group="agent_type" value={r.agent_type} />
                    </p>
                  </TableCell>
                  <TableCell>
                    <p className="text-sm">{r.unit_code || "—"}</p>
                    <p className="text-[11px] text-muted-foreground">
                      <RefLabel group="marketing_fee_trigger" value={r.trigger} />
                    </p>
                  </TableCell>
                  <TableCell className="text-sm">
                    <RefLabel group="scheme_basis" value={r.basis} />
                    <p className="text-[11px] text-muted-foreground">
                      {r.basis === "percent" ? `${r.value}% dari ${formatIDR(r.deal_price)}`
                        : formatIDR(r.value)}
                    </p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.amount_gross)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {formatIDR(r.pph_amount)}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {formatIDR(r.amount_net)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-emerald-700">
                    {formatIDR(r.paid_amount)}
                  </TableCell>
                  <TableCell>
                    <StatusPill status={r.status} group="marketing_fee_status" />
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {formatDateWIB(r.created_at)}
                    </p>
                  </TableCell>
                  <TableCell className="col-actions">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      {canApprove && r.status === "submitted" ? (
                        <>
                          <Button size="sm" data-testid={MFEE.approveBtn} disabled={busy === r.id}
                            onClick={() => act(r, "approve")}>
                            <Check className="mr-1 h-3.5 w-3.5" /> Setujui
                          </Button>
                          <Button size="sm" variant="outline" data-testid={MFEE.rejectBtn}
                            disabled={busy === r.id} onClick={() => act(r, "reject")}>
                            <X className="mr-1 h-3.5 w-3.5" /> Tolak
                          </Button>
                        </>
                      ) : null}
                      {canApprove && r.status === "approved" ? (
                        <Button size="sm" data-testid={MFEE.payBtn} onClick={() => setPayFee(r)}>
                          <Banknote className="mr-1 h-3.5 w-3.5" /> Bayar
                        </Button>
                      ) : null}
                      {r.status === "rejected" && r.reject_reason ? (
                        <span className="text-[11px] text-rose-600">{r.reject_reason}</span>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {(summary?.leaderboard || []).length ? (
        <div data-testid={MFEE.leaderboard} className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="mb-2 flex items-center gap-2">
            <Trophy className="h-4 w-4 text-amber-600" />
            <p className="text-sm font-semibold">Papan Peringkat Mitra</p>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mitra</TableHead>
                <TableHead className="text-right">Deal</TableHead>
                <TableHead className="text-right">Total Fee</TableHead>
                <TableHead className="text-right">Dibayar</TableHead>
                <TableHead className="text-right">Belum Dibayar</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.leaderboard.map((a) => (
                <TableRow key={a.agent_id} data-testid={MFEE.leaderboardRow}>
                  <TableCell>
                    <p className="text-sm font-medium">{a.agent_name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      <RefLabel group="agent_type" value={a.agent_type} />
                    </p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{a.deals_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(a.fee_total)}</TableCell>
                  <TableCell className="text-right tabular-nums text-emerald-700">
                    {formatIDR(a.fee_paid)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-rose-700">
                    {formatIDR(a.fee_outstanding)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}

      <SubmitFeeDialog open={openSubmit} onOpenChange={setOpenSubmit} onSaved={load} />
      <PayFeeDialog fee={payFee} onClose={() => setPayFee(null)} onSaved={load} />
    </div>
  );
}
