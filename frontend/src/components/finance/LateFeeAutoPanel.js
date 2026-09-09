import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlarmClock, Play, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P68 as T } from "@/constants/testIds";

/**
 * Denda keterlambatan TERJADWAL (Fase 68).
 *
 * Mesin denda Fase 58 menunggu tombol; panel ini menampilkan opsi per organisasi
 * (`payment.late.auto_apply`, bawaan MATI) beserta dua remnya, PRATINJAU apa yang akan
 * ditagihkan hari ini (termasuk yang DITAHAN aturan dan sebabnya), dan riwayat putaran.
 * Tombol "Jalankan sekarang" memakai fungsi yang sama dengan penjadwal — idempoten per
 * (termin, bulan), jadi menekan dua kali tidak menagih dua kali.
 */
export default function LateFeeAutoPanel() {
  const { can } = useAuth();
  const canRun = can("late_fee", "create");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/finance/late-fee-auto");
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat status denda terjadwal.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const runNow = async () => {
    setBusy(true);
    try {
      const res = await api.post("/finance/late-fee-auto/run");
      toast.success(res.data.message || "Selesai.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menjalankan."); }
    finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const cfg = data?.config || {};
  const rows = data?.preview?.rows || [];
  const runs = data?.runs || [];

  return (
    <section data-testid={T.autoPanel} className="surface-card space-y-4 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow flex items-center gap-1.5">
            <AlarmClock className="h-3.5 w-3.5" /> Otomatis
          </p>
          <h3 className="section-title">Denda Keterlambatan Terjadwal</h3>
          <p data-testid={T.autoRule} className="page-desc mt-1 text-xs">
            {cfg.rule_sentence}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span data-testid={T.autoState} data-enabled={cfg.enabled ? "true" : "false"}
            className={"status-pill rounded-full border px-2.5 py-1 text-xs font-medium "
              + (cfg.enabled ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-slate-200 bg-slate-50 text-slate-600")}>
            {cfg.enabled ? "Aktif — penjadwal menagihkan tiap hari"
              : "Nonaktif — denda hanya ditagihkan manual"}
          </span>
          {canRun ? (
            <Button data-testid={T.autoRunBtn} size="sm" disabled={busy} onClick={runNow}>
              <Play className="mr-1 h-3.5 w-3.5" />
              {busy ? "Menjalankan…" : "Jalankan sekarang"}
            </Button>
          ) : null}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        {cfg.schedule} Aturan (aktif/nonaktif, hari tunggu {cfg.min_days ?? "-"} hari,
        ambang {formatIDR(cfg.min_amount || 0)}) disetel dari{" "}
        <Link data-testid={T.autoConfigLink} to="/config"
          className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
          <Settings2 className="h-3 w-3" /> Pusat Konfigurasi → Pembayaran
        </Link>.
      </p>

      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Pratinjau hari ini — {data?.preview?.eligible_count || 0} siap ditagihkan
          ({formatIDR(data?.preview?.eligible_total || 0)})
        </p>
        {!rows.length ? (
          <p data-testid={T.autoPreviewEmpty}
            className="surface-sunken px-3 py-2.5 text-xs text-muted-foreground">
            Tidak ada denda yang berlaku hari ini — tidak ada termin yang lewat toleransi
            dengan denda yang belum ditagihkan.
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Unit</TableHead>
                  <TableHead>Pembeli</TableHead>
                  <TableHead>Termin</TableHead>
                  <TableHead className="text-right">Hari lewat toleransi</TableHead>
                  <TableHead className="text-right">Denda</TableHead>
                  <TableHead>Keterangan</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={`${r.deal_id}:${r.item_id}`}
                    data-testid={T.autoPreviewRow} data-eligible={r.eligible}>
                    <TableCell className="font-medium">{r.unit_code || "-"}</TableCell>
                    <TableCell className="text-sm">{r.lead_name || "-"}</TableCell>
                    <TableCell className="text-sm">{r.term}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.days_late}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatIDR(r.amount)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.eligible ? (
                        <span className="font-medium text-emerald-700">
                          Memenuhi aturan otomatis
                        </span>
                      ) : r.hold_reason}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {runs.length ? (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Riwayat putaran terakhir
          </p>
          <div className="space-y-1.5">
            {runs.map((r) => (
              <div key={r.id} data-testid={T.autoRunRow} data-mode={r.mode}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2 text-xs shadow-sm">
                <span className="text-muted-foreground">
                  {formatDateWIB(r.at)} · {r.mode === "auto" ? "penjadwal" : "manual"} ·{" "}
                  {r.actor}
                </span>
                <span className="font-medium tabular-nums">
                  {r.skipped_reason ? r.detail
                    : `${r.charged_count} ditagihkan (${formatIDR(r.charged_total || 0)})`}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
