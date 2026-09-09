import React, { useCallback, useEffect, useState } from "react";
import { ShieldCheck, RefreshCw, AlertTriangle, CheckCircle2, Unlink } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import PhoneHealthCard from "@/components/master/PhoneHealthCard";
import api from "@/services/apiClient";
import { MASTER } from "@/constants/testIds";

/**
 * Kesehatan Data — hasil audit forensik yang bisa dipantau terus:
 * 1. Field kopi (denormalisasi) yang tidak sama dengan master-nya.
 * 2. Nilai enum di luar daftar referensi kanonik.
 * Keduanya adalah penyebab data “berantakan” (tidak bisa difilter/diagregasi).
 */
export default function DataHealthPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/master/data-health");
      setData(r.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat kesehatan data."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const stale = data?.stale_denormalized || [];
  const invalid = data?.invalid_enum_values || [];
  const orphans = data?.orphan_references || [];
  const healthy = !stale.length && !invalid.length && !orphans.length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Pemeriksaan otomatis konsistensi data lintas modul.
        </p>
        <Button data-testid={MASTER.healthRefresh} size="sm" variant="outline" onClick={load}>
          <RefreshCw className="mr-1.5 h-4 w-4" /> Periksa ulang
        </Button>
      </div>

      <PhoneHealthCard />

      {healthy ? (
        <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
          <div>
            <p className="text-sm font-semibold text-emerald-900">Data sehat</p>
            <p className="text-sm text-emerald-800">
              Tidak ada nama/kode salinan yang basi, nilai referensi liar, maupun referensi menggantung.
            </p>
          </div>
        </div>
      ) : null}

      <div data-testid={MASTER.healthStale} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="h-4 w-4 text-primary" />
          Nama/kode salinan basi ({stale.length})
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Nilai yang disimpan ulang di dokumen anak tapi berbeda dari master. Diperbaiki otomatis
          saat startup dan setiap master di-update.
        </p>
        {stale.length ? (
          <div className="mt-3 overflow-hidden">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Koleksi</TableHead><TableHead>ID</TableHead><TableHead>Field</TableHead>
                <TableHead>Tersimpan</TableHead><TableHead>Seharusnya</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {stale.slice(0, 30).map((s, i) => (
                  <TableRow key={`${s.collection}-${s.id}-${i}`}>
                    <TableCell className="text-sm">{s.collection}</TableCell>
                    <TableCell className="font-mono text-xs">{String(s.id).slice(0, 8)}</TableCell>
                    <TableCell className="text-sm">{s.field}</TableCell>
                    <TableCell className="text-sm text-rose-700">{String(s.stored)}</TableCell>
                    <TableCell className="text-sm text-emerald-700">{String(s.master)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : <p className="mt-2 text-sm text-muted-foreground">Tidak ada.</p>}
      </div>

      <div data-testid={MASTER.healthInvalid} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          Nilai referensi tidak dikenal ({invalid.length})
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Nilai di luar daftar kanonik (mis. satuan atau kategori yang diketik bebas sebelum
          dropdown terkontrol dipasang).
        </p>
        {invalid.length ? (
          <div className="mt-3 overflow-hidden">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Koleksi</TableHead><TableHead>Field</TableHead>
                <TableHead>Nilai</TableHead><TableHead className="text-right">Jumlah baris</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {invalid.map((v, i) => (
                  <TableRow key={`${v.collection}-${v.field}-${i}`}>
                    <TableCell className="text-sm">{v.collection}</TableCell>
                    <TableCell className="text-sm">{v.field}</TableCell>
                    <TableCell className="text-sm text-rose-700">{String(v.value)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{v.count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : <p className="mt-2 text-sm text-muted-foreground">Tidak ada.</p>}
      </div>

      <div data-testid="master-health-orphan" className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Unlink className="h-4 w-4 text-rose-600" />
          Referensi menggantung ({orphans.length})
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Dokumen yang menunjuk induk yang sudah tidak ada (mis. tugas yang leadnya sudah hilang).
        </p>
        {orphans.length ? (
          <div className="mt-3 overflow-hidden">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Koleksi</TableHead><TableHead>ID</TableHead><TableHead>Field</TableHead>
                <TableHead>Menunjuk ke</TableHead><TableHead>Tidak ada di</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {orphans.slice(0, 30).map((o, i) => (
                  <TableRow key={`${o.collection}-${o.id}-${i}`}>
                    <TableCell className="text-sm">{o.collection}</TableCell>
                    <TableCell className="font-mono text-xs">{String(o.id).slice(0, 8)}</TableCell>
                    <TableCell className="text-sm">{o.field}</TableCell>
                    <TableCell className="font-mono text-xs">{String(o.value).slice(0, 8)}</TableCell>
                    <TableCell className="text-sm text-rose-700">{o.missing_in}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : <p className="mt-2 text-sm text-muted-foreground">Tidak ada.</p>}
      </div>
    </div>
  );
}
