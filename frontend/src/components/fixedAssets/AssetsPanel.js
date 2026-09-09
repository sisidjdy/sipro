import React, { useCallback, useEffect, useState } from "react";
import { Boxes, Plus, Trash2 } from "lucide-react";
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
import AddAssetDialog from "@/components/fixedAssets/AddAssetDialog";
import AssetDetailSheet from "@/components/fixedAssets/AssetDetailSheet";
import DisposeAssetDialog from "@/components/fixedAssets/DisposeAssetDialog";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ASSETS } from "@/constants/testIds";

/** Register aset tetap + KPI nilai perolehan/akumulasi/nilai buku. */
export default function AssetsPanel() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openAdd, setOpenAdd] = useState(false);
  const [detailId, setDetailId] = useState(null);
  const [dispose, setDispose] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = {};
      if (status) params.status = status;
      if (category) params.category = category;
      const [list, sum] = await Promise.all([
        api.get("/fixed-assets/assets", { params }),
        api.get("/fixed-assets/summary"),
      ]);
      setRows(list.data.data || []);
      setSummary(sum.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar aset tetap.");
    } finally { setLoading(false); }
  }, [status, category]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={ASSETS.panel} className="space-y-5">
      <div data-testid={ASSETS.summary} className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Harga Perolehan" value={summary?.total_cost || 0} tone="primary"
          format="idr" hint={`${summary?.active_count || 0} aset aktif`} />
        <MetricCard label="Akumulasi Penyusutan" value={summary?.total_accumulated || 0}
          tone="amber" format="idr" hint="Akun 1-2200" />
        <MetricCard label="Nilai Buku" value={summary?.total_book_value || 0} tone="emerald"
          format="idr" hint="Perolehan − akumulasi" />
        <MetricCard label="Beban Bulan Ini" value={summary?.depreciation_this_month || 0}
          tone="indigo" format="idr" hint={`Periode ${summary?.current_period || "-"}`} />
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-48 space-y-1">
            <span className="text-xs text-muted-foreground">Status aset</span>
            <ReferenceSelect group="asset_status" value={status} onChange={setStatus}
              allowEmpty emptyLabel="Semua status" testId={ASSETS.statusFilter} />
          </div>
          <div className="w-56 space-y-1">
            <span className="text-xs text-muted-foreground">Kategori aset</span>
            <ReferenceSelect group="asset_category" value={category} onChange={setCategory}
              allowEmpty emptyLabel="Semua kategori" testId={ASSETS.categoryFilter} />
          </div>
        </div>
        <Button data-testid={ASSETS.addBtn} onClick={() => setOpenAdd(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Tambah Aset
        </Button>
      </div>

      {!rows.length ? (
        <div data-testid={ASSETS.empty}>
          <EmptyState icon={Boxes} title="Belum ada aset tetap"
            description="Daftarkan aset (kendaraan, bangunan, peralatan) agar penyusutan bulanannya otomatis terbukukan."
            actionLabel="Tambah Aset" onAction={() => setOpenAdd(true)} />
        </div>
      ) : (
        <div data-testid={ASSETS.table} className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kode</TableHead>
                <TableHead>Nama Aset</TableHead>
                <TableHead>Kategori</TableHead>
                <TableHead>Metode</TableHead>
                <TableHead className="text-right">Perolehan</TableHead>
                <TableHead className="text-right">Akumulasi</TableHead>
                <TableHead className="text-right">Nilai Buku</TableHead>
                <TableHead className="text-right">Susut/bln</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={ASSETS.row} data-status={r.status}>
                  <TableCell className="font-medium">{r.code}</TableCell>
                  <TableCell className="max-w-[240px]">
                    <p className="truncate" title={r.name}>{r.name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {r.location || "—"} · perolehan {formatDateWIB(r.acquired_date)}
                    </p>
                  </TableCell>
                  <TableCell className="text-sm">
                    <RefLabel group="asset_category" value={r.category} />
                  </TableCell>
                  <TableCell className="text-sm">
                    <RefLabel group="depreciation_method" value={r.method} />
                    <p className="text-[11px] text-muted-foreground">
                      {r.useful_life_months ? `${r.useful_life_months} bln` : "tidak disusutkan"}
                    </p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.cost)}</TableCell>
                  <TableCell className="text-right tabular-nums text-amber-700">
                    {formatIDR(r.accumulated_depreciation)}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {formatIDR(r.book_value)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {formatIDR(r.monthly_depreciation)}
                  </TableCell>
                  <TableCell><StatusPill status={r.status} group="asset_status" /></TableCell>
                  <TableCell className="col-actions">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="ghost" data-testid={ASSETS.detailBtn}
                        onClick={() => setDetailId(r.id)}>Detail</Button>
                      {r.status !== "disposed" ? (
                        <Button size="sm" variant="outline" data-testid={ASSETS.disposeBtn}
                          onClick={() => setDispose(r)}>
                          <Trash2 className="mr-1 h-3.5 w-3.5" /> Lepas
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

      <AddAssetDialog open={openAdd} onOpenChange={setOpenAdd} onSaved={load} />
      <AssetDetailSheet assetId={detailId} onClose={() => setDetailId(null)} />
      <DisposeAssetDialog asset={dispose} onClose={() => setDispose(null)} onSaved={load} />
    </div>
  );
}
