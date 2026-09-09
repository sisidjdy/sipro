import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ASSETS } from "@/constants/testIds";

const thisPeriod = () => new Date().toISOString().slice(0, 7);

/**
 * Penyusutan bulanan: satu tombol untuk memposting seluruh aset aktif pada periode
 * terpilih. IDEMPOTEN — menjalankan periode yang sama dua kali tidak membuat jurnal dobel.
 */
export default function DepreciationPanel() {
  const [period, setPeriod] = useState(thisPeriod());
  const [historyPeriod, setHistoryPeriod] = useState("");
  const [rows, setRows] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [amountTotal, setAmountTotal] = useState(0);
  const [summary, setSummary] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [hist, sum] = await Promise.all([
        api.get("/fixed-assets/depreciations", {
          params: historyPeriod ? { period: historyPeriod } : {},
        }),
        api.get("/fixed-assets/summary"),
      ]);
      setRows(hist.data.data || []);
      setPeriods(hist.data.periods || []);
      setAmountTotal(hist.data.amount_total || 0);
      setSummary(sum.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat riwayat penyusutan.");
    } finally { setLoading(false); }
  }, [historyPeriod]);

  useEffect(() => { load(); }, [load]);

  const run = async () => {
    setRunning(true); setResult(null);
    try {
      const res = await api.post("/fixed-assets/depreciation/run", { period });
      const data = res.data.data;
      setResult(data);
      if (data.posted > 0) {
        toast.success(`${data.posted} aset disusutkan, total ${formatIDR(data.total_amount)}.`);
      } else {
        toast.info(`Periode ${data.period} sudah pernah diposting — tidak ada jurnal baru.`);
      }
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan penyusutan.");
    } finally { setRunning(false); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={ASSETS.deprPanel} className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Beban Penyusutan Bulan Ini" value={summary?.depreciation_this_month || 0}
          tone="indigo" format="idr" hint={`Periode ${summary?.current_period || "-"}`} />
        <MetricCard label="Estimasi per Bulan" value={summary?.monthly_run_rate || 0} tone="primary"
          format="idr" hint="Aset aktif yang masih disusutkan" />
        <MetricCard label="Akumulasi Penyusutan" value={summary?.total_accumulated || 0}
          tone="amber" format="idr" hint="Akun 1-2200" />
        <MetricCard label="Aset Habis Disusutkan" value={summary?.fully_depreciated_count || 0}
          tone="muted" hint="Nilai buku = residu" />
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4 shadow-sm">
        <div className="space-y-1.5">
          <Label htmlFor="depr-period">Periode penyusutan</Label>
          <Input id="depr-period" data-testid={ASSETS.deprPeriod} type="month" value={period}
            max={thisPeriod()} onChange={(e) => setPeriod(e.target.value)} className="w-44" />
        </div>
        <Button data-testid={ASSETS.deprRunBtn} disabled={running || !period} onClick={run}>
          <Play className="mr-1.5 h-4 w-4" />
          {running ? "Memproses…" : "Jalankan Penyusutan"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Aman diklik berulang: satu aset hanya bisa punya satu jurnal penyusutan per periode.
        </p>
      </div>

      {result ? (
        <div data-testid={ASSETS.deprResult}
          className={`rounded-xl border p-3 text-sm ${result.posted ? "bg-emerald-50" : "bg-secondary/50"}`}>
          <p className="font-medium">
            Periode {result.period}: {result.posted} aset diposting
            {result.posted ? ` (total ${formatIDR(result.total_amount)})` : ""}, {result.skipped} dilewati.
          </p>
          {!result.posted ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Tidak ada jurnal baru — periode ini sudah diposting sebelumnya atau tidak ada aset
              yang masih perlu disusutkan.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <span className="text-xs text-muted-foreground">Riwayat periode</span>
          <Select value={historyPeriod || "__all__"}
            onValueChange={(v) => setHistoryPeriod(v === "__all__" ? "" : v)}>
            <SelectTrigger data-testid={ASSETS.deprHistoryFilter} className="w-48">
              <SelectValue placeholder="Semua periode" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Semua periode</SelectItem>
              {periods.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <p className="text-sm text-muted-foreground">
          Total beban tampil: <span className="font-semibold tabular-nums">{formatIDR(amountTotal)}</span>
        </p>
      </div>

      {!rows.length ? (
        <EmptyState icon={CalendarClock} title="Belum ada penyusutan terposting"
          description="Pilih periode lalu klik Jalankan Penyusutan untuk membukukan beban penyusutan bulanan." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Periode</TableHead>
                <TableHead>Aset</TableHead>
                <TableHead>Jurnal</TableHead>
                <TableHead className="text-right">Beban</TableHead>
                <TableHead className="text-right">Akumulasi</TableHead>
                <TableHead className="text-right">Nilai Buku</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={ASSETS.deprRow}>
                  <TableCell className="font-medium">{r.period}</TableCell>
                  <TableCell>
                    <p className="text-sm">{r.asset_name}</p>
                    <p className="text-[11px] text-muted-foreground">{r.asset_code}</p>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.entry_no}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.amount)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.accumulated_after)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.book_value_after)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
