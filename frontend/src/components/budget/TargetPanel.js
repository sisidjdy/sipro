import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2, History, Pencil, Plus, RefreshCw, Target, XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import StatusPill from "@/components/patterns/StatusPill";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import RecalcDialog from "@/components/budget/RecalcDialog";
import TargetDialog from "@/components/budget/TargetDialog";
import TargetPeriodTable from "@/components/budget/TargetPeriodTable";
import { Count, MissingNote, Money, Pct } from "@/components/budget/parts";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * TargetPanel — target unit & pendapatan per proyek (Fase 45, `docs/v2/32` §2).
 *
 * Yang dijaga panel ini:
 *   * **satu target resmi**: hanya satu target induk boleh AKTIF per proyek (dipaksakan server);
 *   * **angka bisa dijelaskan**: rumus metode, carry over, dan jejak penyesuaian ditampilkan
 *     — bukan hanya hasil akhirnya;
 *   * **jujur saat kosong**: tanpa target aktif, panel tidak menggambar “0 unit, 100%”,
 *     melainkan mengajak membuat target.
 */
export default function TargetPanel({ projectId }) {
  const { can } = useAuth();
  const { labelOf } = useReference();
  const canCreate = can("targets", "create");
  const canUpdate = can("targets", "update");
  const canManage = can("targets", "manage");

  const [list, setList] = useState(null);
  const [selected, setSelected] = useState(null);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dialogFor, setDialogFor] = useState(undefined);   // undefined=tutup, null=baru
  const [recalcFor, setRecalcFor] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const r = await api.get("/targets", { params: { project_id: projectId } });
      const rows = r.data.data || [];
      setList(rows);
      const keep = rows.find((t) => t.id === selected) || rows.find((t) => t.status === "active")
        || rows[0];
      setSelected(keep?.id || null);
      if (keep) {
        const p = await api.get(`/targets/${keep.id}/progress`);
        setProgress(p.data.data);
      } else setProgress(null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat target proyek.");
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const pick = async (id) => {
    setSelected(id);
    try {
      const p = await api.get(`/targets/${id}/progress`);
      setProgress(p.data.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memuat progres target."); }
  };

  const changeStatus = async (target, action) => {
    // Rute ditulis EKSPLISIT (bukan `${action}` di dalam URL): gate `verify_api_contract`
    // mencocokkan setiap panggilan frontend ke route backend, dan URL yang dirakit dari
    // variabel membuat pencocokan itu mustahil — artinya tombol mati tidak akan tertangkap.
    const call = action === "activate"
      ? api.post(`/targets/${target.id}/activate`,
        { reason: "Target dijadikan rencana resmi" })
      : api.post(`/targets/${target.id}/close`,
        { reason: "Target ditutup dari layar Target & Budget" });
    try {
      await call;
      toast.success(action === "activate" ? "Target diaktifkan." : "Target ditutup.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengubah status target.");
    }
  };

  if (!projectId) {
    return <EmptyState icon={Target} title="Pilih proyek"
      description="Pilih proyek untuk menyusun target unit & pendapatan beserta rencana bulanannya." />;
  }
  if (loading && !list) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const current = (list || []).find((t) => t.id === selected);
  const totals = progress?.totals || {};

  return (
    <div data-testid={BUDGET.targetPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">Target proyek</p>
          <p className="text-[12px] text-muted-foreground">
            Realisasi dibaca dari deal yang benar-benar tercatat — tidak pernah diinput ulang.
          </p>
        </div>
        {canCreate ? (
          <Button size="sm" data-testid={BUDGET.targetCreate} onClick={() => setDialogFor(null)}>
            <Plus className="mr-1.5 h-4 w-4" /> Buat Target
          </Button>
        ) : null}
      </div>

      {!list?.length ? (
        <EmptyState icon={Target} title="Belum ada target untuk proyek ini"
          description="Target menjadikan rencana penjualan bisa diukur per bulan: berapa unit & berapa pendapatan, dengan penyesuaian otomatis tiap awal bulan."
          actionLabel={canCreate ? "Buat Target" : undefined}
          onAction={() => setDialogFor(null)} />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {list.map((t) => (
              <button key={t.id} type="button" data-testid={BUDGET.targetRow}
                data-active={t.id === selected ? "true" : "false"}
                onClick={() => pick(t.id)}
                className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  t.id === selected ? "border-primary bg-primary/5" : "bg-card hover:bg-secondary"}`}>
                <span className="flex items-center gap-2 font-medium">
                  {t.name}
                  <StatusPill status={t.status} group="target_status" />
                </span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  {labelOf("target_method", t.method)} · {t.horizon?.start} s/d {t.horizon?.end}
                  {t.owner_email ? ` · ${t.owner_email}` : ""}
                </span>
              </button>
            ))}
          </div>

          {current && progress ? (
            <div className="space-y-4">
              <div data-testid={BUDGET.targetSummary}
                className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <MetricCard label="Target unit" value={totals.unit_target} tone="primary" />
                <MetricCard label="Realisasi unit" value={totals.unit_actual_total}
                  tone="emerald"
                  hint={progress.achievement_pct !== null
                    ? `pencapaian ${progress.achievement_pct}%` : "pencapaian belum bisa dihitung"} />
                <MetricCard label="Target pendapatan" value={totals.revenue_target} format="idr"
                  tone="indigo" />
                <MetricCard label="Realisasi pendapatan" value={totals.revenue_actual_total}
                  format="idr" tone="sky"
                  hint={progress.revenue_achievement_pct !== null
                    ? `pencapaian ${progress.revenue_achievement_pct}%`
                    : "pencapaian belum bisa dihitung"} />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {canUpdate ? (
                  <Button size="sm" variant="secondary" data-testid={BUDGET.targetEdit}
                    onClick={() => setDialogFor(current)}>
                    <Pencil className="mr-1.5 h-4 w-4" /> Ubah target
                  </Button>
                ) : null}
                {canUpdate ? (
                  <Button size="sm" variant="secondary" data-testid={BUDGET.targetRecalcBtn}
                    onClick={() => setRecalcFor(current)}>
                    <RefreshCw className="mr-1.5 h-4 w-4" /> Hitung ulang
                  </Button>
                ) : null}
                {canManage && current.status !== "active" ? (
                  <Button size="sm" data-testid={BUDGET.targetActivate}
                    onClick={() => setConfirm({ target: current, action: "activate" })}>
                    <CheckCircle2 className="mr-1.5 h-4 w-4" /> Aktifkan
                  </Button>
                ) : null}
                {canManage && current.status === "active" ? (
                  <Button size="sm" variant="outline" data-testid={BUDGET.targetClose}
                    onClick={() => setConfirm({ target: current, action: "close" })}>
                    <XCircle className="mr-1.5 h-4 w-4" /> Tutup target
                  </Button>
                ) : null}
              </div>

              <div className="rounded-lg border bg-secondary/40 p-3 text-[12px]">
                <p className="font-medium">
                  Metode: {labelOf("target_method", progress.method)}
                </p>
                <p className="mt-0.5 font-mono text-[11px]">{progress.formula}</p>
                <p className="mt-1 text-muted-foreground">
                  Harga rata-rata yang dipakai: <Money value={progress.avg_price_used} />
                  {" · "}Kekurangan dipindahkan (carry over):{" "}
                  <Count value={totals.carry_over} suffix="unit" />
                  {" · "}{totals.keep_total_ok === true
                    ? `Σ rencana ke depan + realisasi lampau = ${totals.unit_plan_future
                      + totals.unit_actual_past} dari ${totals.unit_target} unit`
                    : "Σ rencana belum bisa dijumlahkan (rencana belum bisa dihitung)"}
                </p>
              </div>

              <MissingNote items={progress.missing} testId={BUDGET.targetMissing}
                title="Target ini belum lengkap karena:" />
              {(progress.warnings || []).map((w, i) => (
                <p key={i}
                  className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
                  {w}
                </p>
              ))}

              {progress.projection ? (
                <div data-testid={BUDGET.projection}
                  className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-[12px] text-sky-900">
                  Proyeksi habis terjual:{" "}
                  <span className="font-semibold">
                    {progress.projection.sold_out_period || "sudah tercapai"}
                  </span>
                  {" "}({progress.projection.months_needed} bulan lagi pada kecepatan{" "}
                  {progress.projection.per_month} unit/bulan — dasar:{" "}
                  {progress.projection.basis})
                  {progress.projection.beyond_horizon
                    ? " — MELEWATI horizon target yang ditetapkan." : ""}
                </div>
              ) : null}

              <TargetPeriodTable periods={progress.periods} />

              {(progress.history || []).length ? (
                <div data-testid={BUDGET.history} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                  <p className="flex items-center gap-1.5 text-sm font-semibold">
                    <History className="h-4 w-4" /> Jejak penyesuaian target
                  </p>
                  <ul className="mt-2 space-y-1.5 text-[12px]">
                    {[...progress.history].reverse().map((h, i) => (
                      <li key={i} className="border-b pb-1.5 last:border-0">
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {String(h.at || "").slice(0, 16).replace("T", " ")}
                        </span>{" "}
                        <span className="font-medium">{h.by}</span> — {h.reason}
                        {h.changed_periods
                          ? ` (${h.changed_periods} bulan berubah${h.carry_over
                            ? `, dipindahkan ${h.carry_over} unit` : ""})`
                          : " (tidak ada bulan berubah)"}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {progress.coverage ? (
                <p className="text-[11px] text-muted-foreground">
                  Cakupan realisasi: {progress.coverage.deals} deal terjual
                  {progress.coverage.tanpa_tanggal
                    ? ` · ${progress.coverage.tanpa_tanggal} tanpa tanggal booking (tidak masuk bulan mana pun)`
                    : ""}
                  {progress.coverage.tanpa_harga
                    ? ` · ${progress.coverage.tanpa_harga} tanpa harga (tidak masuk realisasi pendapatan)`
                    : ""}
                </p>
              ) : null}
            </div>
          ) : null}
        </>
      )}

      <TargetDialog projectId={projectId} target={dialogFor || null}
        open={dialogFor !== undefined} onOpenChange={(v) => !v && setDialogFor(undefined)}
        onDone={load} />
      <RecalcDialog target={recalcFor || {}} open={!!recalcFor}
        onOpenChange={(v) => !v && setRecalcFor(null)} onDone={load} />
      <ConfirmDialog open={!!confirm} onOpenChange={(v) => !v && setConfirm(null)}
        title={confirm?.action === "activate" ? "Aktifkan target ini?" : "Tutup target ini?"}
        description={confirm?.action === "activate"
          ? "Target aktif menjadi rencana RESMI proyek dan dipakai dashboard. Target induk aktif lain harus ditutup lebih dulu."
          : "Target yang ditutup tidak bisa diubah lagi karena laporan historis mengacu padanya."}
        confirmLabel={confirm?.action === "activate" ? "Aktifkan" : "Tutup target"}
        onConfirm={() => { changeStatus(confirm.target, confirm.action); setConfirm(null); }} />
    </div>
  );
}
