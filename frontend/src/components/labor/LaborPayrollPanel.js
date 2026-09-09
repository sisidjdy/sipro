import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Coins, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import ProjectSelect from "@/components/construction/ProjectSelect";
import PayrollDetailSheet from "@/components/labor/PayrollDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LABOR } from "@/constants/testIds";

const monthStart = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
};
const today = () => new Date().toISOString().slice(0, 10);

/**
 * LaborPayrollPanel (Fase 47D) — rekap upah periode: dari absensi menjadi pembayaran.
 *
 * Rekap TIDAK menghitung ulang apa pun: ia menjumlahkan baris absensi yang sudah ada
 * (tie-out per orang per hari), sehingga total yang dibayar selalu bisa dilacak ke
 * kehadiran yang dicatat mandor. Periode yang bertumpang ditolak server — upah tidak boleh
 * dibayar dua kali untuk hari yang sama.
 *
 * `mode="field"` dipakai di hub Pembangunan (menyusun & mengajukan); `mode="finance"`
 * dipakai di Keuangan (menyetujui & membayar).
 */
export default function LaborPayrollPanel({ projectId: fixedProject, mode = "field",
  onChanged }) {
  const { can } = useAuth();
  const [projectId, setProjectId] = useState(fixedProject || null);
  const [rows, setRows] = useState(null);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [buildOpen, setBuildOpen] = useState(false);
  const [period, setPeriod] = useState({ start: monthStart(), end: today(), note: "" });
  const [busy, setBusy] = useState(false);
  const [detailId, setDetailId] = useState(null);

  // Izin EFEKTIF dari `GET /auth/me`, bukan daftar nama peran yang disalin ke layar:
  // matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, dan daftar salinan tidak ikut
  // berubah sehingga layar & server bisa berbeda pendapat (tombol mati / tombol hilang).
  // Pasangannya sama dengan yang dipaksakan router: menyusun rekap = `labor:create`,
  // mengajukan = `labor:update`, menyetujui/membayar = `labor:approve`.
  const canRecord = can("labor", "create");
  const canSubmit = can("labor", "update");
  const canApprove = can("labor", "approve");

  useEffect(() => { if (fixedProject) setProjectId(fixedProject); }, [fixedProject]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/labor/payrolls", {
        params: { ...(projectId ? { project_id: projectId } : {}), limit: 50 },
      });
      setRows(res.data.data || []);
      setSummary(res.data.summary || {});
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rekap upah.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const build = async () => {
    if (!projectId) { toast.error("Pilih proyek lebih dulu."); return; }
    setBusy(true);
    try {
      const res = await api.post("/labor/payrolls", {
        project_id: projectId, period_start: period.start, period_end: period.end,
        note: period.note.trim() || null,
      });
      toast.success(res.data.message || "Rekap upah dibuat.");
      setBuildOpen(false);
      load();
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyusun rekap upah.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={LABOR.payrollPanel} className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-heading text-lg font-semibold">Rekap upah periode</h3>
          <p className="text-sm text-muted-foreground">
            {mode === "finance"
              ? "Rekap yang diajukan lapangan: setujui, tolak beralasan, atau bayar (melahirkan jurnal)."
              : "Kumpulkan absensi menjadi satu rekap, lalu ajukan ke keuangan."}
          </p>
        </div>
        <div className="flex items-end gap-2">
          {!fixedProject ? (
            <div className="space-y-1.5">
              <Label>Proyek</Label>
              <ProjectSelect value={projectId} onChange={setProjectId}
                testId="labor-payroll-project-select" />
            </div>
          ) : null}
          {canRecord ? (
            <Button data-testid={LABOR.payrollBuildBtn} disabled={!projectId}
              onClick={() => setBuildOpen(true)}>
              <Plus className="mr-1.5 h-4 w-4" /> Susun rekap
            </Button>
          ) : null}
        </div>
      </div>

      {summary.submitted ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {summary.submitted} rekap menunggu keputusan keuangan
          {summary.unpaid_amount ? (
            <> · nilai belum dibayar <MoneyText value={summary.unpaid_amount} /></>
          ) : null}.
        </p>
      ) : null}

      {loading ? <LoadingCards count={2} /> : null}
      {error ? <ErrorState message={error} onRetry={load} /> : null}

      {!loading && !error && !(rows || []).length ? (
        <EmptyState icon={Coins} title="Belum ada rekap upah"
          description={canRecord
            ? "Susun rekap dari absensi yang sudah dicatat. Rekap kosong tidak akan dibuat — isi absensi harian lebih dulu."
            : "Rekap upah dibuat oleh pelaksana/manajer proyek dari absensi harian. Belum ada yang diajukan ke keuangan."}
          actionLabel={canRecord ? "Susun rekap" : ""}
          onAction={canRecord ? () => setBuildOpen(true) : null} />
      ) : null}

      {!loading && !error && (rows || []).length ? (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Nomor</th>
                <th className="px-3 py-2 text-left">Periode</th>
                <th className="px-3 py-2 text-right">Orang / hari</th>
                <th className="px-3 py-2 text-right">Total upah</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((p) => (
                <tr key={p.id} data-testid={LABOR.payrollRow} data-state={p.state}>
                  <td className="px-3 py-2">
                    <p className="font-mono text-xs font-medium">{p.no}</p>
                    <p className="text-xs text-muted-foreground">{p.project_name}</p>
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {formatDateWIB(p.period_start)} – {formatDateWIB(p.period_end)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {p.worker_count} / {p.days_total}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <MoneyText value={p.total} className="font-medium" />
                  </td>
                  <td className="px-3 py-2">
                    <StatusPill status={p.state} group="payroll_state" />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="outline" data-testid={LABOR.payrollDetailBtn}
                      data-payroll={p.id} aria-label={`Buka rekap upah ${p.no}`}
                      onClick={() => setDetailId(p.id)}>
                      Buka
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <Dialog open={buildOpen} onOpenChange={setBuildOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Susun rekap upah</DialogTitle>
            <DialogDescription>
              Semua absensi berupah dalam periode ini dikumpulkan. Periode yang bertumpang
              dengan rekap lain akan ditolak agar upah tidak dibayar dua kali.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="payroll-from">Tanggal mulai</Label>
                <Input id="payroll-from" type="date" data-testid={LABOR.payrollFrom}
                  value={period.start}
                  onChange={(e) => setPeriod((p) => ({ ...p, start: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="payroll-to">Tanggal akhir</Label>
                <Input id="payroll-to" type="date" data-testid={LABOR.payrollTo}
                  value={period.end}
                  onChange={(e) => setPeriod((p) => ({ ...p, end: e.target.value }))} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="payroll-note">Catatan</Label>
              <Textarea id="payroll-note" rows={2} value={period.note}
                placeholder="Mis. upah minggu ke-2 Agustus, pekerjaan struktur blok A."
                onChange={(e) => setPeriod((p) => ({ ...p, note: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBuildOpen(false)}>Batal</Button>
            <Button data-testid={LABOR.payrollBuildSubmit} disabled={busy} onClick={build}>
              {busy ? "Menyusun…" : "Susun rekap"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PayrollDetailSheet payrollId={detailId} open={!!detailId}
        onOpenChange={(v) => !v && setDetailId(null)} canSubmit={canSubmit}
        canApprove={canApprove} onChanged={() => { load(); onChanged?.(); }} />
    </div>
  );
}
