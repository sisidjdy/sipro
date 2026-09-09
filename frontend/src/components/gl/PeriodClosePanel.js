import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Lock, Unlock, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

const MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
  "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
const label = (p) => `${MONTHS[Number(p.slice(5, 7)) - 1]} ${p.slice(0, 4)}`;

/**
 * Tutup periode: setelah ditutup, jurnal MANUAL bertanggal di periode itu ditolak
 * backend. Posting OTOMATIS dari transaksi nyata tidak dibuang — tanggalnya digeser
 * ke periode terbuka berikutnya dengan catatan pada memo (jejak audit tetap utuh).
 * Membuka kembali periode dibatasi untuk owner/super admin (kontrol SoD).
 */
export default function PeriodClosePanel() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  // `POST /gl/periods/reopen` menuntut `gl:approve`. Daftar peran lama menyembunyikan
  // tombol ini dari Manajer Keuangan padahal ia punya `gl:manage` (mencakup approve).
  const canReopen = can("gl", "approve");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [target, setTarget] = useState(null); // {period, action}
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/periods");
      setRows(r.data.data || []);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat status periode."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    if (!target) return;
    setBusy(true);
    try {
      const url = target.action === "close" ? "/gl/periods/close" : "/gl/periods/reopen";
      await api.post(url, { period: target.period });
      toast.success(target.action === "close"
        ? `Periode ${label(target.period)} ditutup.`
        : `Periode ${label(target.period)} dibuka kembali.`);
      setTarget(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi periode gagal.");
    } finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={GL.periodsPanel} className="space-y-4">
      <div>
        <p className="section-title">Tutup Periode Akuntansi</p>
        <p className="text-xs text-muted-foreground">
          Menutup periode mencegah jurnal manual mengubah angka historis. Transaksi nyata yang
          terlambat masuk akan otomatis dibukukan di periode terbuka berikutnya.
        </p>
      </div>

      {!rows.length ? (
        <EmptyState icon={ShieldCheck} title="Belum ada periode dengan jurnal"
          description="Periode akan muncul otomatis setelah ada jurnal (transaksi atau penyesuaian)." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Periode</TableHead>
              <TableHead className="text-right">Jurnal</TableHead>
              <TableHead className="text-right">Pendapatan</TableHead>
              <TableHead className="text-right">Beban</TableHead>
              <TableHead className="text-right">Laba (Rugi)</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="col-actions-head text-right">Aksi</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.period} data-testid={GL.periodRow} data-period={r.period}
                  data-status={r.status}>
                  <TableCell className="text-sm font-medium">{label(r.period)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{r.journals}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.revenue)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.expense)}</TableCell>
                  <TableCell className={`text-right tabular-nums text-sm font-medium ${r.net_income >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                    {formatIDR(r.net_income)}
                  </TableCell>
                  <TableCell>
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${r.status === "closed" ? "border-slate-300 bg-slate-100 text-slate-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
                      {r.status === "closed" ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
                      {r.status === "closed" ? "Ditutup" : "Terbuka"}
                    </span>
                    {r.status === "closed" && r.closed_by ? (
                      <p className="mt-1 text-[10px] text-muted-foreground">
                        oleh {r.closed_by} · {formatDateTimeWIB(r.closed_at)}
                      </p>
                    ) : null}
                  </TableCell>
                  <TableCell className="col-actions text-right">
                    {r.status === "open" ? (
                      <Button data-testid={GL.periodCloseBtn} data-period={r.period}
                        aria-label={`Tutup periode ${label(r.period)}`} size="sm" variant="outline"
                        onClick={() => setTarget({ period: r.period, action: "close" })}>
                        <Lock className="mr-1.5 h-3.5 w-3.5" /> Tutup
                      </Button>
                    ) : canReopen ? (
                      <Button data-testid={GL.periodReopenBtn} data-period={r.period}
                        aria-label={`Buka kembali periode ${label(r.period)}`} size="sm" variant="outline"
                        onClick={() => setTarget({ period: r.period, action: "reopen" })}>
                        <Unlock className="mr-1.5 h-3.5 w-3.5" /> Buka kembali
                      </Button>
                    ) : (
                      <span className="text-[11px] text-muted-foreground">khusus owner</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <ConfirmDialog open={!!target} onOpenChange={(v) => !v && setTarget(null)}
        title={target?.action === "close"
          ? `Tutup periode ${target ? label(target.period) : ""}?`
          : `Buka kembali periode ${target ? label(target.period) : ""}?`}
        description={target?.action === "close"
          ? "Setelah ditutup, jurnal manual bertanggal di periode ini akan ditolak. Posting otomatis dari transaksi nyata akan digeser ke periode terbuka berikutnya."
          : "Periode akan bisa menerima jurnal manual lagi. Aksi ini tercatat di jejak audit."}
        confirmLabel={target?.action === "close" ? "Ya, tutup periode" : "Ya, buka kembali"}
        destructive={target?.action === "close"} busy={busy} onConfirm={run}
        testId="gl-period-confirm" />
    </div>
  );
}
