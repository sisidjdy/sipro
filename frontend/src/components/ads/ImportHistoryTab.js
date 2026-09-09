import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { History } from "lucide-react";

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import ImportReport from "@/components/ads/ImportReport";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ADS } from "@/constants/testIds";

/**
 * ImportHistoryTab — audit setiap impor biaya iklan: siapa, kapan, berkas apa (sidik jari
 * SHA-256), berapa baris masuk/diperbarui/ditolak, dan pratinjau yang belum disimpan.
 *
 * Kenapa riwayat ini penting: biaya iklan adalah angka yang dipakai menghitung CPL/CAC/ROAS.
 * Kalau suatu hari angkanya terlihat aneh, pertanyaan pertama selalu “dari berkas mana angka
 * ini datang?” — dan itu harus bisa dijawab tanpa menebak.
 */
export default function ImportHistoryTab() {
  const { labelOf } = useReference();
  const { can } = useAuth();
  const canCommit = can("ads", "update");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/ads/spend/imports", { params: { limit: 50 } });
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat riwayat impor.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (row) => {
    try {
      const res = await api.get(`/ads/spend/import/${row.id}`);
      setDetail(res.data.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuka laporan impor.");
    }
  };

  const commit = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/ads/spend/import/${detail.id}/commit`);
      setDetail(res.data.data);
      const a = res.data.data?.applied || {};
      toast.success(`Tersimpan: ${a.inserted || 0} baru, ${a.updated || 0} diperbarui.`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan impor.");
    } finally { setBusy(false); }
  };

  if (loading && !rows.length) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!rows.length) {
    return (
      <EmptyState icon={History} title="Belum ada impor biaya iklan"
        description="Setiap impor CSV (termasuk pratinjau yang tidak disimpan) akan tercatat di
          sini beserta sidik jari berkasnya, supaya asal setiap angka biaya bisa dilacak." />
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Pratinjau yang belum disimpan tetap tercatat (status <em>Pratinjau</em>) dan masih bisa
        disimpan dari sini — jadi pekerjaan validasi tidak pernah hilang karena dialog tertutup.
      </p>
      <div data-testid={ADS.importsTable} className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left">Berkas</th>
              <th className="px-3 py-2 text-left">Waktu</th>
              <th className="px-3 py-2 text-left">Oleh</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-right">Baris</th>
              {/* Judul kolom memakai SSOT `ads_row_status` supaya tidak berbeda dengan teks
                  status di dalam laporan impor. */}
              <th className="px-3 py-2 text-right">{labelOf("ads_row_status", "rejected")}</th>
              <th className="px-3 py-2 text-right">Tersimpan</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} data-testid={ADS.importsRow} data-status={r.status}
                className="cursor-pointer border-t hover:bg-secondary/50"
                onClick={() => openDetail(r)}>
                <td className="px-3 py-2">
                  <p className="font-medium">{r.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {(r.platforms || []).map((p) => labelOf("ad_platform", p)).join(", ")
                      || "platform tidak terbaca"}
                  </p>
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {formatDateTimeWIB(r.created_at)}
                </td>
                <td className="px-3 py-2 text-xs">{r.imported_by}</td>
                <td className="px-3 py-2">
                  <StatusPill status={r.status} group="ads_import_status" />
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{r.summary?.total || 0}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {r.summary?.rejected
                    ? <span className="text-rose-700">{r.summary.rejected}</span>
                    : 0}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {r.applied
                    ? `${r.applied.inserted || 0}+${r.applied.updated || 0}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent data-testid={ADS.importDetail}
          className="max-h-[92vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Laporan impor — {detail?.filename}</DialogTitle>
          </DialogHeader>
          <ImportReport report={detail} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetail(null)}>Tutup</Button>
            {canCommit && detail?.status === "preview" ? (
              <Button onClick={commit} disabled={busy}>
                {busy ? "Menyimpan…" : "Simpan baris yang lolos"}
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
