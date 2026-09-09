import React, { useCallback, useEffect, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ASSETS } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}

/** Detail aset: identitas, riwayat penyusutan terposting, dan proyeksi jadwal sisa. */
export default function AssetDetailSheet({ assetId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!assetId) return;
    setLoading(true); setError("");
    try {
      const res = await api.get(`/fixed-assets/assets/${assetId}`);
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat detail aset.");
    } finally { setLoading(false); }
  }, [assetId]);

  useEffect(() => { load(); }, [load]);

  if (!assetId) return null;
  const a = data?.data;

  return (
    <Sheet open onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent data-testid={ASSETS.detailSheet} className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {a ? `${a.code} — ${a.name}` : "Detail Aset"}
            {a ? <StatusPill status={a.status} group="asset_status" /> : null}
          </SheetTitle>
          <SheetDescription>
            Riwayat penyusutan terposting dan proyeksi bulan-bulan berikutnya.
          </SheetDescription>
        </SheetHeader>

        {loading ? <LoadingCards count={2} /> : error ? <ErrorState message={error} onRetry={load} /> : a ? (
          <div className="mt-4 space-y-4">
            <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <Row label="Kategori" value={<RefLabel group="asset_category" value={a.category} />} />
              <Row label="Kelompok fiskal" value={<RefLabel group="asset_tax_group" value={a.tax_group} />} />
              <Row label="Metode" value={<RefLabel group="depreciation_method" value={a.method} />} />
              <Row label="Umur manfaat" value={a.useful_life_months ? `${a.useful_life_months} bulan` : "—"} />
              <Row label="Tanggal perolehan" value={formatDateWIB(a.acquired_date)} />
              <Row label="Harga perolehan" value={formatIDR(a.cost)} />
              <Row label="Nilai residu" value={formatIDR(a.salvage_value)} />
              <Row label="Akumulasi penyusutan" value={formatIDR(a.accumulated_depreciation)} />
              <Row label="Nilai buku" value={formatIDR(a.book_value)} />
              <Row label="Penyusutan/bulan" value={formatIDR(data.monthly_depreciation)} />
              <Row label="Sumber dana" value={<RefLabel group="asset_funding" value={a.funding} />} />
              <Row label="Vendor" value={a.vendor || "—"} />
              <Row label="Lokasi" value={a.location || "—"} />
              <Row label="Proyek" value={a.project_name || "—"} />
              {a.status === "disposed" ? (
                <>
                  <Row label="Tanggal pelepasan" value={formatDateWIB(a.disposed_date)} />
                  <Row label="Hasil pelepasan" value={formatIDR(a.disposal_proceeds)} />
                  <Row label={a.disposal_gain_loss >= 0 ? "Laba pelepasan" : "Rugi pelepasan"}
                    value={formatIDR(Math.abs(a.disposal_gain_loss || 0))} />
                </>
              ) : null}
            </div>

            <div>
              <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                Riwayat penyusutan terposting ({(data.history || []).length})
              </p>
              {(data.history || []).length ? (
                <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Periode</TableHead>
                        <TableHead>Jurnal</TableHead>
                        <TableHead className="text-right">Beban</TableHead>
                        <TableHead className="text-right">Akumulasi</TableHead>
                        <TableHead className="text-right">Nilai Buku</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.history.map((h) => (
                        <TableRow key={h.id} data-testid={ASSETS.historyRow}>
                          <TableCell>{h.period}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{h.entry_no}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(h.amount)}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(h.accumulated_after)}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(h.book_value_after)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="rounded-lg border bg-secondary/30 p-3 text-sm text-muted-foreground">
                  Belum ada penyusutan terposting untuk aset ini.
                </p>
              )}
            </div>

            <div>
              <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                Proyeksi jadwal penyusutan ({(data.schedule || []).length} bulan)
              </p>
              {(data.schedule || []).length ? (
                <div className="max-h-72 overflow-y-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Periode</TableHead>
                        <TableHead className="text-right">Beban</TableHead>
                        <TableHead className="text-right">Akumulasi</TableHead>
                        <TableHead className="text-right">Nilai Buku</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.schedule.map((s) => (
                        <TableRow key={s.period} data-testid={ASSETS.scheduleRow}>
                          <TableCell>{s.period}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(s.amount)}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(s.accumulated)}</TableCell>
                          <TableCell className="text-right tabular-nums">{formatIDR(s.book_value)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="rounded-lg border bg-secondary/30 p-3 text-sm text-muted-foreground">
                  Tidak ada proyeksi (aset sudah habis disusutkan, dilepas, atau tidak disusutkan).
                </p>
              )}
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
