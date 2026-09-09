import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Lock, Unlock, ShieldAlert, RefreshCw, ExternalLink, ClipboardCheck, CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
  "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
export const monthLabel = (p) => (String(p || "").length === 7
  ? `${MONTHS[Number(String(p).slice(5, 7)) - 1]} ${String(p).slice(0, 4)}` : "-");
// Nada warna pill (bukan label): label manusia tetap datang dari Kamus Data backend.
const TONE = { ok: "completed", blocking: "overdue", warning: "high", missing_data: "snoozed" };
const thisMonth = () => new Date().toISOString().slice(0, 7);

/**
 * Penutupan buku bulanan (Fase 49A) — daftar periksa yang MENAHAN, bukan tombol yang
 * diam-diam berhasil. Setiap pemeriksaan yang gagal menyebut sebab + jumlah + tautan ke
 * halaman sumber, sehingga penutupan bisa dituntaskan tanpa menebak. Menerobos hanya untuk
 * peran berwenang, wajib beralasan ≥10 huruf, dan alasannya ikut terbaca di laporan owner.
 */
export default function ClosingChecklistPanel({ onChanged }) {
  const { can } = useAuth();
  const canOverride = can("gl", "close_override");
  const canReopen = can("gl", "approve");
  const [period, setPeriod] = useState(thisMonth());
  const [periods, setPeriods] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [held, setHeld] = useState("");
  const [busy, setBusy] = useState(false);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(async (p) => {
    setLoading(true); setError(""); setHeld("");
    try {
      const [chk, list] = await Promise.all([
        api.get("/gl/periods/close-check", { params: { period: p } }),
        api.get("/gl/periods", { params: { limit: 12 } }),
      ]);
      setData(chk.data.data || null);
      setPeriods(list.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar periksa tutup buku.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(period); }, [load, period]);

  const closePeriod = async (override) => {
    setBusy(true); setHeld("");
    try {
      const body = override
        ? { period, override: true, override_reason: reason.trim() }
        : { period };
      await api.post("/gl/periods/close", body);
      toast.success(`Periode ${monthLabel(period)} ditutup.`);
      setOverrideOpen(false); setReason("");
      await load(period);
      onChanged && onChanged();
    } catch (e) {
      const detail = e?.response?.data?.detail || "Penutupan periode gagal.";
      setHeld(detail);
      toast.error(detail);
    } finally { setBusy(false); }
  };

  const reopen = async () => {
    setBusy(true);
    try {
      await api.post("/gl/periods/reopen", { period });
      toast.success(`Periode ${monthLabel(period)} dibuka kembali.`);
      await load(period);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuka kembali periode.");
    } finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={() => load(period)} />;

  const closed = data?.status === "closed";
  const blocking = (data?.items || []).filter((i) => i.state === "blocking");

  return (
    <div data-testid={P49.closingPanel} className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="p49-closing-month">Periode (bulan buku)</Label>
          <Input id="p49-closing-month" type="month" className="w-[170px]"
            data-testid={P49.closingPeriodInput} value={period}
            onChange={(e) => setPeriod(e.target.value || thisMonth())} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {periods.slice(0, 6).map((p) => (
            <Button key={p.period} type="button" size="sm" variant={p.period === period ? "default" : "outline"}
              className="h-8 text-xs" data-testid={P49.closingPeriodQuick} data-period={p.period}
              aria-label={`Pilih periode ${monthLabel(p.period)}`} onClick={() => setPeriod(p.period)}>
              {monthLabel(p.period)}
              {p.status === "closed" ? <Lock className="ml-1 h-3 w-3" /> : null}
            </Button>
          ))}
          <Button type="button" size="icon" variant="outline" data-testid={P49.closingRefresh}
            aria-label="Muat ulang daftar periksa" title="Muat ulang" onClick={() => load(period)}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div data-testid={P49.closingStatus} data-status={data?.status}
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3.5 shadow-[var(--shadow-card)]">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <StatusPill status={closed ? "closed" : "open"}
              label={closed ? "Periode DITUTUP" : "Periode TERBUKA"} />
            <p className="section-title">{monthLabel(period)}</p>
          </div>
          <p className="text-xs text-muted-foreground">{data?.detail}</p>
          {closed && data?.closed_by ? (
            <p className="text-[11px] text-muted-foreground">
              Ditutup oleh {data.closed_by} · {formatDateTimeWIB(data.closed_at)}
            </p>
          ) : null}
          {data?.override_reason ? (
            <p className="text-[11px] font-medium text-amber-800">
              Ditutup dengan terobosan oleh {data.override_by}: “{data.override_reason}”
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {!closed ? (
            <Button size="sm" data-testid={P49.closingCloseBtn} disabled={busy}
              onClick={() => closePeriod(false)}>
              <Lock className="mr-1.5 h-3.5 w-3.5" /> Tutup Periode
            </Button>
          ) : null}
          {!closed && blocking.length && canOverride ? (
            <Button size="sm" variant="outline" data-testid={P49.closingOverrideBtn} disabled={busy}
              onClick={() => setOverrideOpen(true)}>
              <ShieldAlert className="mr-1.5 h-3.5 w-3.5" /> Tutup dengan Terobosan
            </Button>
          ) : null}
          {closed && canReopen ? (
            <Button size="sm" variant="outline" data-testid={P49.closingReopenBtn} disabled={busy}
              onClick={reopen}>
              <Unlock className="mr-1.5 h-3.5 w-3.5" /> Buka Kembali
            </Button>
          ) : null}
        </div>
      </div>

      {held ? (
        <div data-testid={P49.closingHoldBanner}
          className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-sm text-rose-900">
          <p className="font-semibold">Penutupan ditahan — sebabnya disebut apa adanya:</p>
          <p className="mt-1 whitespace-pre-line">{held}</p>
          {!canOverride ? (
            <p className="mt-2 text-xs">
              Menerobos daftar periksa hanya untuk Manajer Keuangan/Direksi. Tuntaskan dulu
              pemeriksaan di bawah, atau minta persetujuan yang berwenang.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Pendapatan periode" value={data?.revenue} format="idr" tone="emerald" />
        <MetricCard label="Beban periode" value={data?.expense} format="idr" tone="rose" />
        <MetricCard label="Laba (rugi) periode" value={data?.net_income} format="idr"
          tone={(data?.net_income || 0) >= 0 ? "primary" : "rose"} />
        <MetricCard label="Pemeriksaan menahan" value={`${data?.blocking_count || 0} menahan · ${data?.warning_count || 0} perhatian`}
          tone={data?.can_close ? "emerald" : "amber"}
          hint={data?.can_close ? "Daftar periksa bersih" : "Tuntaskan sebelum menutup"} />
      </div>

      <div className="space-y-2">
        <p className="flex items-center gap-1.5 font-heading text-sm font-semibold">
          <ClipboardCheck className="h-4 w-4 text-primary" /> Daftar periksa tutup buku
        </p>
        {(data?.items || []).map((item) => (
          <div key={item.code} data-testid={P49.closingItem} data-code={item.code}
            data-state={item.state}
            className="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                {item.state === "ok"
                  ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                  : <ShieldAlert className={`h-4 w-4 shrink-0 ${item.state === "blocking" ? "text-rose-600" : "text-amber-600"}`} />}
                <p className="text-sm font-medium">{item.label}</p>
                <StatusPill status={item.state} group="closing_check_state"
                  tone={TONE[item.state] || "snoozed"} />
              </div>
              <p className="text-xs text-muted-foreground">{item.detail}</p>
              {item.amount ? (
                <p className="text-xs font-medium tabular-nums text-slate-700">
                  Nilai tertahan: {formatIDR(item.amount)}
                </p>
              ) : null}
            </div>
            {item.link ? (
              <a href={item.link} data-testid={P49.closingItemLink} data-code={item.code}
                className="inline-flex items-center gap-1 rounded-lg border bg-card px-2.5 py-1.5 text-xs font-medium text-primary hover:bg-accent shadow-[var(--shadow-card)]">
                Buka sumbernya <ExternalLink className="h-3 w-3" />
              </a>
            ) : null}
          </div>
        ))}
      </div>

      <Dialog open={overrideOpen} onOpenChange={(v) => { setOverrideOpen(v); if (!v) setReason(""); }}>
        <DialogContent data-testid={P49.closingOverrideDialog}>
          <DialogHeader>
            <DialogTitle>Tutup {monthLabel(period)} dengan terobosan</DialogTitle>
            <DialogDescription>
              {blocking.length} pemeriksaan masih menahan. Alasan tertulis wajib (minimal 10
              huruf), tercatat di jejak audit, terbaca di paket laporan owner, dan melahirkan
              tugas tinjauan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <ul className="list-disc space-y-1 rounded-lg border border-amber-200 bg-amber-50 p-3 pl-6 text-xs text-amber-900">
              {blocking.map((b) => <li key={b.code}>{b.label} — {b.detail}</li>)}
            </ul>
            <div className="space-y-1.5">
              <Label htmlFor="p49-override-reason">Alasan menerobos (≥10 huruf)</Label>
              <Textarea id="p49-override-reason" rows={3} value={reason}
                data-testid={P49.closingOverrideReason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="mis. Mutasi bank dicocokkan bulan depan sesuai memo direksi 12/2026" />
              <p className="text-[11px] text-muted-foreground">{reason.trim().length}/10 huruf</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={busy} data-testid={P49.closingOverrideCancel}
              onClick={() => setOverrideOpen(false)}>Batal</Button>
            <Button data-testid={P49.closingOverrideSubmit} disabled={busy || reason.trim().length < 10}
              onClick={() => closePeriod(true)}>
              {busy ? "Memproses…" : "Tutup paksa & catat alasan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
