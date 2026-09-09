import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarCheck, ShieldAlert, Undo2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const TONE = { open: "open", closed: "closed", reopened: "high" };

/**
 * Tutup tahun buku (Fase 49B) — laba/rugi tahun berjalan dipindahkan ke Laba Ditahan lewat
 * jurnal penutup yang SEIMBANG dan tidak bisa dobel (idempoten). Membuka kembali tahun tidak
 * menghapus jurnal itu: sistem membuat jurnal PEMBALIK berjejak, sehingga ekuitas yang pernah
 * dilaporkan tetap bisa ditelusuri.
 */
export default function YearClosingPanel({ onChanged }) {
  const { can } = useAuth();
  const canClose = can("gl", "year_close");
  const [years, setYears] = useState([]);
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [check, setCheck] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState(null); // {action: "close"|"reopen", year}
  const [reason, setReason] = useState("");

  const load = useCallback(async (y) => {
    setLoading(true); setError("");
    try {
      const [list, chk] = await Promise.all([
        api.get("/gl/year"),
        api.get("/gl/year/check", { params: { year: y } }),
      ]);
      setYears(list.data.data || []);
      setCheck(chk.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat status tutup tahun.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(year); }, [load, year]);

  const run = async () => {
    if (!dialog) return;
    setBusy(true);
    try {
      const url = dialog.action === "close" ? "/gl/year/close" : "/gl/year/reopen";
      const body = dialog.action === "close"
        ? { year: dialog.year, note: reason.trim() || null }
        : { year: dialog.year, reason: reason.trim() };
      const res = await api.post(url, body);
      const doc = res.data.data || {};
      if (dialog.action === "close") {
        toast.success(doc.idempotent
          ? `Tahun ${dialog.year} sudah ditutup sebelumnya — tidak ada jurnal baru dibuat.`
          : `Tahun ${dialog.year} ditutup lewat jurnal ${doc.entry_no}.`);
      } else {
        toast.success(`Tahun ${dialog.year} dibuka kembali; jurnal penutup dibalik oleh ${doc.reversal_entry_no}.`);
      }
      setDialog(null); setReason("");
      await load(year);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi tutup tahun gagal.");
    } finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={() => load(year)} />;

  const yearList = years.length ? years : [{ year, state: "open" }];
  const needReason = dialog?.action === "reopen";

  return (
    <div data-testid={P49.yearPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 font-heading text-base font-semibold">
            <CalendarCheck className="h-4 w-4 text-primary" /> Tutup Tahun Buku
          </p>
          <p className="text-xs text-muted-foreground">
            Laba/rugi tahun berjalan dipindahkan ke Laba Ditahan lewat jurnal penutup seimbang.
            Menutup dua kali tidak membuat jurnal baru; membuka kembali membuat jurnal pembalik.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {yearList.map((y) => (
            <Button key={y.year} type="button" size="sm" className="h-8 text-xs"
              variant={y.year === year ? "default" : "outline"} data-testid={P49.yearQuick}
              data-year={y.year} aria-label={`Pilih tahun buku ${y.year}`}
              onClick={() => setYear(y.year)}>
              {y.year}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label={`Laba (rugi) ${year}`} value={check?.pl?.net_income} format="idr"
          tone={(check?.pl?.net_income || 0) >= 0 ? "emerald" : "rose"} />
        <MetricCard label="Pendapatan setahun" value={check?.pl?.revenue} format="idr" tone="primary" />
        <MetricCard label="Beban setahun" value={check?.pl?.expense} format="idr" tone="amber" />
        <MetricCard label="Status tutup tahun" value={check?.state === "closed" ? "Sudah ditutup"
          : check?.state === "reopened" ? "Dibuka kembali" : "Belum ditutup"}
          tone={check?.can_close ? "emerald" : "slate"} hint={check?.detail} />
      </div>

      <div className="space-y-2">
        {(check?.items || []).map((item) => (
          <div key={item.code} data-testid={P49.yearCheckItem} data-code={item.code}
            data-state={item.state}
            className="flex flex-wrap items-start gap-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
            {item.state === "ok"
              ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              : <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />}
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium">{item.label}</p>
                <StatusPill status={item.state} group="closing_check_state"
                  tone={item.state === "ok" ? "completed" : "overdue"} />
              </div>
              <p className="text-xs text-muted-foreground">{item.detail}</p>
              {item.link ? (
                <a href={item.link} className="text-xs font-medium text-primary hover:underline">
                  Buka halaman yang menahan
                </a>
              ) : null}
            </div>
          </div>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <Table>
          <TableHeader><TableRow>
            <TableHead>Tahun</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Laba (rugi)</TableHead>
            <TableHead>Jurnal penutup</TableHead>
            <TableHead>Jejak</TableHead>
            <TableHead className="col-actions-head text-right">Aksi</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {yearList.map((y) => (
              <TableRow key={y.year} data-testid={P49.yearRow} data-year={y.year} data-state={y.state}>
                <TableCell className="text-sm font-medium">{y.year}</TableCell>
                <TableCell>
                  <StatusPill status={y.state} group="year_closing_state"
                    tone={TONE[y.state] || "open"} />
                </TableCell>
                <TableCell className="text-right tabular-nums text-sm">
                  {formatIDR(y.net_income ?? y.current_net_income)}
                </TableCell>
                <TableCell className="text-sm tabular-nums text-muted-foreground">
                  {y.entry_no || "-"}
                </TableCell>
                <TableCell className="max-w-[260px] text-[11px] text-muted-foreground">
                  {y.closed_by ? <p>Ditutup {y.closed_by} · {formatDateTimeWIB(y.closed_at)}</p> : null}
                  {y.reversal_entry_no ? (
                    <p className="text-amber-800">Dibalik {y.reversal_entry_no} — “{y.reopen_reason}”</p>
                  ) : null}
                  {!y.closed_by && !y.reversal_entry_no ? "Belum ada jejak penutupan" : null}
                </TableCell>
                <TableCell className="col-actions text-right">
                  {!canClose ? (
                    <span className="text-[11px] text-muted-foreground">khusus Direksi</span>
                  ) : y.state === "closed" ? (
                    <Button size="sm" variant="outline" data-testid={P49.yearReopenBtn}
                      data-year={y.year} disabled={busy}
                      onClick={() => { setDialog({ action: "reopen", year: y.year }); setReason(""); }}>
                      <Undo2 className="mr-1 h-3.5 w-3.5" /> Buka kembali
                    </Button>
                  ) : (
                    <Button size="sm" data-testid={P49.yearCloseBtn} data-year={y.year} disabled={busy}
                      onClick={() => { setDialog({ action: "close", year: y.year }); setReason(""); }}>
                      <CalendarCheck className="mr-1 h-3.5 w-3.5" /> Tutup tahun
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!dialog} onOpenChange={(v) => { if (!v) { setDialog(null); setReason(""); } }}>
        <DialogContent data-testid={P49.yearDialog}>
          <DialogHeader>
            <DialogTitle>
              {needReason ? `Buka kembali tahun ${dialog?.year}?` : `Tutup tahun ${dialog?.year}?`}
            </DialogTitle>
            <DialogDescription>
              {needReason
                ? "Jurnal penutup tahun akan DIBALIK (bukan dihapus) dan ekuitas yang sudah dilaporkan berubah. Alasan wajib minimal 10 huruf."
                : "Laba/rugi tahun ini dipindahkan ke Laba Ditahan lewat satu jurnal penutup seimbang. Bila tahun ini sudah ditutup, sistem tidak membuat jurnal kedua."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="p49-year-reason">
              {needReason ? "Alasan membuka kembali (≥10 huruf)" : "Catatan (opsional)"}
            </Label>
            <Textarea id="p49-year-reason" rows={3} value={reason} data-testid={P49.yearReason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={needReason
                ? "mis. Koreksi penyusutan tahun lalu atas temuan audit eksternal"
                : "mis. Tutup tahun setelah audit internal selesai"} />
            {needReason ? (
              <p className="text-[11px] text-muted-foreground">{reason.trim().length}/10 huruf</p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={busy} data-testid={P49.yearCancel}
              onClick={() => setDialog(null)}>Batal</Button>
            <Button data-testid={P49.yearSubmit} onClick={run}
              disabled={busy || (needReason && reason.trim().length < 10)}>
              {busy ? "Memproses…" : needReason ? "Buka kembali & balik jurnal" : "Tutup tahun"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
