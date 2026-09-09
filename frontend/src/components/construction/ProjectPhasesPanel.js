import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, HardHat, Image as ImageIcon, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import KurvaSChart from "@/components/construction/KurvaSChart";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import { photoSrc } from "@/utils/photoSrc";
import api from "@/services/apiClient";
import { CONSTRUCTION } from "@/constants/testIds";

const PHASE_TONE = { not_started: "draft", done: "completed", qc_hold: "lost", in_progress: "in_progress" };

/**
 * Pekerjaan KAWASAN (infrastruktur): jalan, drainase, saluran, gerbang — pekerjaan yang
 * memang milik proyek, BUKAN rumah tertentu.
 *
 * Progres rumah per unit TIDAK lagi diambil dari sini (dulu angka proyek ditimpa ke semua
 * unit sehingga tiap rumah tampak sama). Rumah punya jadwal & bukti sendiri di tab
 * "Monitoring Unit".
 */
export default function ProjectPhasesPanel({ projectId, onChanged }) {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canUpdate = can("construction", "update");
  const [phases, setPhases] = useState([]);
  const [overall, setOverall] = useState(0);
  const [curve, setCurve] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const [p, l] = await Promise.all([
        api.get(`/construction/project/${projectId}/phases`),
        api.get(`/construction/project/${projectId}/logs`),
      ]);
      setPhases(p.data.data || []);
      setOverall(p.data.overall || 0);
      setCurve(p.data.curve);
      setLogs(l.data.data || []);
      const e = {};
      (p.data.data || []).forEach((ph) => { e[ph.id] = ph.progress; });
      setEdits(e);
    } catch (err) {
      setError(err?.response?.data?.detail || "Gagal memuat pekerjaan kawasan.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const remove = async (ph) => {
    if (!window.confirm(`Hapus fase '${ph.name}'? Ditolak bila sudah ada progres/inspeksi/permintaan material.`)) return;
    setBusy(ph.id);
    try {
      await api.delete(`/construction/phases/${ph.id}`);
      toast.success(`Fase '${ph.name}' dihapus.`);
      load(); onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghapus fase.");
    } finally { setBusy(null); }
  };

  const save = async (ph) => {
    setBusy(ph.id);
    try {
      const res = await api.post(`/construction/phases/${ph.id}/progress`,
        { progress: Number(edits[ph.id]) });
      toast.success(`Progres kawasan '${ph.name}' → ${res.data.data.progress}%.`);
      load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan progres.");
    } finally { setBusy(null); }
  };

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
        Bagian ini khusus <b>pekerjaan kawasan</b> (jalan, drainase, gerbang, saluran).
        Progres tiap rumah dihitung dari jadwal & bukti pekerjaan unit di tab
        <b> Monitoring Unit</b> — bukan dari angka di halaman ini.
      </div>

      {curve?.behind ? (
        <div data-testid="curve-deviation-alert"
          className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" />
          <div className="text-sm">
            <p className="font-semibold text-rose-800">Pekerjaan kawasan tertinggal jadwal</p>
            <p className="text-rose-700">
              Deviasi {Math.abs(curve.deviation)}% di bawah rencana. Tugas korektif otomatis
              dibuat untuk Manajer Proyek.
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="mb-1 flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold">
              <HardHat className="h-4 w-4 text-primary" /> Progres kawasan (berbobot)
            </h3>
            <span className="font-heading text-2xl font-bold tabular-nums text-primary">
              {overall}%
            </span>
          </div>
          <Progress value={overall} className="h-3" />
          <div className="mt-4 space-y-3">
            {phases.map((ph) => (
              <div key={ph.id} data-testid={CONSTRUCTION.phaseRow}
                className="rounded-lg border bg-background p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{ph.name}
                    <span className="ml-1 text-xs text-muted-foreground">bobot {ph.weight}%</span>
                    {ph.work_category ? (
                      <span data-testid="phase-synced-badge" data-phase-id={ph.id} className="ml-2 rounded border border-teal-200 bg-teal-50 px-1.5 py-0.5 text-[10px] text-teal-800"
                        title="Progres dihitung otomatis dari langkah jadwal unit berkategori ini">
                        sinkron dari unit · {ph.work_category}
                      </span>
                    ) : null}
                  </span>
                  <div className="flex items-center gap-1">
                    <StatusPill status={ph.status} group="construction_status"
                      tone={PHASE_TONE[ph.status] || "in_progress"} />
                    {canUpdate ? (
                      <Button data-testid="phase-delete" size="icon" variant="ghost" className="h-7 w-7"
                        aria-label={`Hapus fase ${ph.name}`} title="Hapus fase" disabled={busy === ph.id}
                        onClick={() => remove(ph)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
                    ) : null}
                  </div>
                </div>
                <div className="mt-2"><Progress value={ph.progress} className="h-1.5" /></div>
                {canUpdate && !ph.work_category ? (
                  <div className="mt-2 flex items-center gap-2">
                    <Input data-testid={CONSTRUCTION.progressInput} type="number" min={0} max={100}
                      aria-label={`Progres pekerjaan kawasan ${ph.name} (%)`}
                      className="h-8 w-24" value={edits[ph.id] ?? ph.progress}
                      onChange={(e) => setEdits((s) => ({ ...s, [ph.id]: e.target.value }))} />
                    <span className="text-xs text-muted-foreground">%</span>
                    <Button data-testid={CONSTRUCTION.progressSubmit} size="sm" variant="outline"
                      onClick={() => save(ph)} disabled={busy === ph.id}>
                      <Save className="mr-1 h-3.5 w-3.5" /> Simpan
                    </Button>
                  </div>
                ) : ph.work_category ? (
                  <p className="mt-1 text-[11px] text-muted-foreground">{ph.progress}% — dihitung dari item pekerjaan unit yang terverifikasi (kategori {ph.work_category}); tidak diisi manual.</p>
                ) : null}
              </div>
            ))}
            {!phases.length ? (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                Belum ada pekerjaan kawasan pada proyek ini.
              </p>
            ) : null}
          </div>
        </div>
        <KurvaSChart curve={curve} />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">Riwayat log lapangan kawasan</h3>
        {!logs.length ? (
          <p className="rounded-xl border border-dashed bg-card p-4 text-sm text-muted-foreground">
            Belum ada log lapangan kawasan pada proyek ini.
          </p>
        ) : (
          <div className="space-y-2">
            {logs.slice(0, 10).map((lg) => (
              <div key={lg.id} data-testid={CONSTRUCTION.logItem} data-log={lg.id}
                className="flex gap-3 rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
                {lg.photo ? (
                  <img src={photoSrc(lg.photo)} alt="Dokumentasi log kawasan"
                    className="h-14 w-14 shrink-0 rounded-md border object-cover" />
                ) : (
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border bg-secondary text-muted-foreground">
                    <ImageIcon className="h-5 w-5" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill
                      status={lg.type === "qc"
                        ? (lg.result === "fail" ? "failed" : "passed") : "in_progress"}
                      label={lg.type === "qc"
                        ? `QC ${lg.result === "fail" ? "gagal" : "lulus"}`
                        : `Progres ${lg.progress}%`} />
                    <span className="text-xs text-muted-foreground">
                      {formatDateTimeWIB(lg.created_at)}
                    </span>
                  </div>
                  {lg.note ? <p className="mt-1 text-sm">{lg.note}</p> : null}
                  <p className="text-[11px] text-muted-foreground">{lg.actor}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
