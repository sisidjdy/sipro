import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Building2, Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import VendorDialog from "@/components/vendors/VendorDialog";
import VendorDetailSheet from "@/components/vendors/VendorDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { VENDOR as T } from "@/constants/testIds";

/**
 * VendorsPanel (Fase 48A) — MASTER vendor, pengganti “vendor sebagai teks bebas”.
 *
 * Sebelum fase ini, nama vendor hanya string di PO/tagihan: satu rekanan bisa muncul sebagai
 * tiga ejaan berbeda, riwayatnya tidak bisa dijumlahkan, dan tidak ada NPWP/termin bayar/
 * rekening yang bisa dipakai keuangan. Kolom “dipakai” di tabel ini memperlihatkan jumlah PO
 * & nilainya — angka NYATA dari basis data, bukan label kosong.
 */
export default function VendorsPanel() {
  const { can } = useAuth();
  const canCreate = can("vendors", "create");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState(null);   // {mode, vendor}
  const [detailId, setDetailId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/vendors", { params: { q: q || undefined } });
      setRows(r.data.data || []);
      setSummary(r.data.summary || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar vendor.");
    } finally { setLoading(false); }
  }, [q]);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid={T.panel} className="space-y-4">
      {summary ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Vendor terdaftar" value={summary.total} tone="primary" />
          <MetricCard label="Aktif" value={summary.active} tone="emerald" />
          <MetricCard label="Pernah dipakai PO" value={summary.with_po} tone="indigo" />
          <MetricCard label="Nilai PO" value={summary.po_value} tone="amber" format="idr" />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} className="search-field pl-9"
            placeholder="Cari nama atau kode vendor…" aria-label="Cari vendor" />
        </div>
        {canCreate ? (
          <Button data-testid={T.addBtn} size="sm" onClick={() => setDialog({ mode: "create" })}>
            <Plus className="mr-1.5 h-4 w-4" /> Daftarkan vendor
          </Button>
        ) : null}
      </div>

      {loading ? <LoadingCards count={3} /> : error ? <ErrorState message={error} onRetry={load} />
        : !rows.length ? (
          <EmptyState icon={Building2} title="Belum ada vendor terdaftar"
            description={"Daftarkan pemasok/penyedia jasa di sini supaya PO tidak lagi menyebut "
              + "vendor sebagai teks bebas — riwayat, harga, dan penilaiannya baru bisa "
              + "dikumpulkan setelah vendor punya master."} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Kode / Nama</TableHead>
                <TableHead>Kategori</TableHead>
                <TableHead>Termin</TableHead>
                <TableHead className="text-right">PO</TableHead>
                <TableHead className="text-right">Nilai PO</TableHead>
                <TableHead className="text-right">Utang berjalan</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head" />
              </TableRow></TableHeader>
              <TableBody>
                {rows.map((v) => (
                  <TableRow key={v.id} data-testid={T.row} data-vendor={v.code}>
                    <TableCell>
                      <p className="font-medium">{v.name}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">{v.code}
                        {v.pic_name ? ` · PIC ${v.pic_name}` : ""}</p>
                    </TableCell>
                    <TableCell className="text-sm">
                      <RefLabel group="vendor_category" value={v.category} />
                    </TableCell>
                    <TableCell className="text-sm tabular-nums">{v.payment_terms_days} hari</TableCell>
                    <TableCell className="text-right tabular-nums">{v.usage?.po_count ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatIDR(v.usage?.po_value)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatIDR(v.usage?.bill_outstanding)}</TableCell>
                    <TableCell>
                      <StatusPill status={v.is_active ? "active" : "archived"}
                        label={v.is_active ? "Aktif" : "Nonaktif"} />
                    </TableCell>
                    <TableCell className="col-actions text-right">
                      <Button data-testid={T.detailBtn} size="sm" variant="outline"
                        onClick={() => setDetailId(v.id)}>Buka</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

      <VendorDialog open={!!dialog} mode={dialog?.mode} vendor={dialog?.vendor}
        onOpenChange={(v) => !v && setDialog(null)}
        onDone={() => { setDialog(null); load(); toast.success("Vendor tersimpan."); }} />
      <VendorDetailSheet vendorId={detailId} onOpenChange={(v) => !v && setDetailId(null)}
        onChanged={load}
        onEdit={(vendor) => { setDetailId(null); setDialog({ mode: "edit", vendor }); }} />
    </div>
  );
}
