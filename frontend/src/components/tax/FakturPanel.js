import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, Download, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import IssueFakturDialog from "@/components/tax/IssueFakturDialog";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { TAX } from "@/constants/testIds";

export default function FakturPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/tax/faktur");
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat faktur pajak.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const downloadPdf = async (f) => {
    setBusyId(f.id);
    try {
      const res = await api.get(`/tax/faktur/${f.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (e) {
      toast.error("Gagal mengunduh PDF faktur.");
    } finally { setBusyId(null); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={TAX.fakturPanel} className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Faktur Pajak Keluaran atas penjualan unit.</p>
        <Button size="sm" data-testid={TAX.issueFakturBtn} onClick={() => setDialogOpen(true)}>
          <Plus className="mr-1 h-4 w-4" /> Terbitkan Faktur
        </Button>
      </div>

      {!rows.length ? (
        <EmptyState icon={FileText} title="Belum ada faktur pajak"
          description="Terbitkan Faktur Pajak Keluaran untuk deal yang sudah memiliki jadwal AR." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No. Seri Faktur</TableHead>
                <TableHead>Pembeli</TableHead>
                <TableHead>NPWP</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead className="text-right">DPP</TableHead>
                <TableHead className="text-right">PPN</TableHead>
                <TableHead>Terbit</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head text-right">PDF</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((f) => (
                <TableRow key={f.id} data-testid={TAX.fakturRow}>
                  <TableCell className="font-medium tabular-nums">{f.number}</TableCell>
                  <TableCell>{f.buyer_name || "-"}</TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">{f.buyer_npwp || "-"}</TableCell>
                  <TableCell>{f.unit_code || "-"}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(f.dpp)}</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold text-primary">{formatIDR(f.ppn)}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDateWIB(f.issued_at)}</TableCell>
                  <TableCell><StatusPill status={f.status} group="faktur_status" /></TableCell>
                  <TableCell className="col-actions">
                    <div className="flex justify-end">
                      <Button size="sm" variant="outline" data-testid={TAX.fakturPdfBtn}
                        onClick={() => downloadPdf(f)} disabled={busyId === f.id}>
                        <Download className="mr-1 h-3.5 w-3.5" /> PDF
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <IssueFakturDialog open={dialogOpen} onOpenChange={setDialogOpen} onDone={load} />
    </div>
  );
}
