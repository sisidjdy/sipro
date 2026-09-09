import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BellRing, Gavel, CheckCircle2, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import ArDetailSheet from "@/components/finance/ArDetailSheet";
import { FINANCE, P91 } from "@/constants/testIds";
import RefLabel from "@/components/patterns/RefLabel";

const BUCKET_BADGE = {
  overdue: "bg-rose-50 text-rose-700 border-rose-200",
  due_soon: "bg-amber-50 text-amber-800 border-amber-200",
  current: "bg-slate-50 text-slate-600 border-slate-200",
};

export default function CollectionsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [detailDealId, setDetailDealId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/finance/collections");
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat worklist penagihan.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const remind = async (row) => {
    setBusy(row.deal_id + ":remind");
    try {
      await api.post(`/finance/collections/${row.deal_id}/remind`, {});
      toast.success(`Pengingat dikirim ke ${row.assigned_to || "sales"} (+ tugas dibuat).`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim pengingat."); }
    finally { setBusy(""); }
  };

  const lateFee = async (row) => {
    setBusy(row.deal_id + ":fee");
    try {
      const res = await api.post(`/finance/collections/${row.deal_id}/late-fee`, {});
      toast.success(`Denda ${formatIDR(res.data?.data?.denda || 0)} diterapkan pada AR.`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menerapkan denda."); }
    finally { setBusy(""); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const t = data.totals || {};
  const rows = data.rows || [];

  return (
    <div data-testid={FINANCE.collectionsPanel} className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Total Tunggakan" value={t.overdue_total} tone="rose" format="idr" hint={`${t.count_overdue || 0} akun`} />
        <MetricCard label="Jatuh Tempo Dekat" value={t.due_soon_total} tone="amber" format="idr" hint="≤ 14 hari" />
        <MetricCard label="Estimasi Denda" value={t.denda_total} tone="primary" format="idr" hint={`${data.config?.denda_rate_pct_month || 0}%/bln`} />
        <MetricCard label="Total Akun AR" value={t.count} tone="indigo" hint="Belum lunas" />
      </div>

      {!rows.length ? (
        <EmptyState icon={CheckCircle2} title="Tidak ada tagihan tertunggak"
          description="Semua piutang lancar. Worklist penagihan akan menampilkan akun yang menunggak / jatuh tempo dekat." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Unit</TableHead>
                <TableHead>Pembeli</TableHead>
                <TableHead>Jatuh Tempo</TableHead>
                <TableHead className="text-right">Telat</TableHead>
                <TableHead className="text-right">Tunggakan</TableHead>
                <TableHead className="text-right">Denda (est.)</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.deal_id} data-testid={FINANCE.collectionRow} data-deal={r.deal_id}
                  className="cursor-pointer" onClick={() => setDetailDealId(r.deal_id)}
                  title="Klik untuk membuka rincian termin & riwayat pembayaran">
                  <TableCell className="font-medium">{r.unit_code || "-"}</TableCell>
                  <TableCell>
                    <div>{r.lead_name || "-"}</div>
                    <div className="text-[11px] text-muted-foreground">{r.assigned_to || "-"}</div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDateWIB(r.next_due)}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.days_overdue > 0 ? `${r.days_overdue} hr` : "-"}</TableCell>
                  <TableCell className="text-right tabular-nums text-rose-700">{formatIDR(r.overdue_amount)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.denda_estimate)}</TableCell>
                  <TableCell>
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${BUCKET_BADGE[r.bucket] || BUCKET_BADGE.current}`}>
                      <RefLabel group="collection_bucket" value={r.bucket} />
                    </span>
                    {r.reminded_at ? <div className="mt-0.5 text-[10px] text-muted-foreground">Diingatkan {formatDateWIB(r.reminded_at)}</div> : null}
                  </TableCell>
                  <TableCell className="col-actions">
                    <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <Button size="sm" variant="ghost" data-testid={P91.collectionRowDetail}
                        onClick={() => setDetailDealId(r.deal_id)}>
                        <Eye className="mr-1 h-3.5 w-3.5" /> Detail
                      </Button>
                      <Button size="sm" variant="outline" data-testid={FINANCE.remindBtn}
                        onClick={() => remind(r)} disabled={busy === r.deal_id + ":remind"}>
                        <BellRing className="mr-1 h-3.5 w-3.5" /> Ingatkan
                      </Button>
                      {r.overdue_amount > 0 ? (
                        <Button size="sm" variant="outline" className="text-rose-700" data-testid={FINANCE.lateFeeBtn}
                          onClick={() => lateFee(r)} disabled={busy === r.deal_id + ":fee"}>
                          <Gavel className="mr-1 h-3.5 w-3.5" /> Denda
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
      <p className="text-[11px] italic text-muted-foreground">{data.note}</p>
      <ArDetailSheet dealId={detailDealId} open={!!detailDealId}
        onOpenChange={(v) => !v && setDetailDealId(null)} onChanged={load} />
    </div>
  );
}
