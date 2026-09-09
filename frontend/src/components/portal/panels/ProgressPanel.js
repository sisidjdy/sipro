import React, { useEffect, useState } from "react";
import { Camera, CalendarCheck2, Wrench } from "lucide-react";
import BeforeAfterCompare from "@/components/patterns/BeforeAfterCompare";
import PhotoGallery from "@/components/patterns/PhotoGallery";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import portalApi from "@/services/portalClient";
import { PORTAL } from "@/constants/testIds";

const shortDate = (v) => (v
  ? new Date(`${String(v).slice(0, 10)}T00:00:00`).toLocaleDateString("id-ID",
    { day: "numeric", month: "short", year: "numeric" })
  : "-");

/**
 * Progres RUMAH pembeli.
 *
 * Sebelum Fase 31 panel ini menampilkan progres FASE PROYEK (jalan & drainase kawasan)
 * seolah-olah itu progres rumah pembeli — angkanya sama untuk semua unit. Sekarang yang
 * utama adalah jadwal rumahnya sendiri (tahapan per minggu yang sudah diverifikasi
 * pengawas), sementara pekerjaan kawasan ditampilkan terpisah dan dilabeli jujur.
 */
export default function ProgressPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try {
      const res = await portalApi.get("/portal/progress");
      setData(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat progres.");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data?.length) {
    return (
      <p className="rounded-xl border bg-white p-6 text-center text-sm text-slate-500">
        Belum ada data progres.
      </p>
    );
  }

  return (
    <div data-testid={PORTAL.progressPanel} className="space-y-6">
      {data.map((u) => (
        <div key={u.deal_id} className="rounded-xl border bg-white p-5">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
            <p className="section-title">Rumah {u.unit_code}</p>
            <span className="text-sm font-semibold tabular-nums text-indigo-600">
              {u.build ? u.build.progress : u.construction_progress}%
            </span>
          </div>
          <div className="mb-2 h-3 w-full overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-indigo-600"
              style={{ width: `${u.build ? u.build.progress : u.construction_progress}%` }} />
          </div>

          {u.build ? (
            <div data-testid={PORTAL.buildMilestones}>
              <p className="mb-3 text-xs text-slate-500">
                Dihitung dari pekerjaan yang sudah diperiksa & disetujui pengawas.
                Rencana selesai {shortDate(u.build.target_finish_date)}
                {u.build.deviation_days
                  ? ` — saat ini ${u.build.deviation_days} hari lebih lambat dari rencana`
                  : " — sesuai rencana"}.
              </p>
              <ol className="space-y-2">
                {(u.build.milestones || []).map((m) => (
                  <li key={m.week} data-week={m.week}
                    className="rounded-lg border bg-slate-50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium">
                        Minggu {m.week}
                        <span className="ml-2 text-xs font-normal text-slate-500">
                          {m.items_done}/{m.items_total} pekerjaan selesai
                        </span>
                      </p>
                      <div className="flex items-center gap-2">
                        {m.late ? (
                          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">
                            melewati rencana
                          </span>
                        ) : null}
                        <StatusPill status={m.status}
                          label={m.status === "done" ? "Selesai"
                            : m.status === "in_progress" ? "Dikerjakan" : "Belum mulai"}
                          tone={m.status === "done" ? "completed"
                            : m.status === "in_progress" ? "in_progress" : "draft"} />
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-slate-600">
                      {(m.works || []).join(" · ")}
                    </p>
                    <p className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                      <CalendarCheck2 className="h-3 w-3" />
                      Rencana selesai {shortDate(m.planned_finish)}
                      {m.done_at ? ` · disetujui ${shortDate(m.done_at)}` : ""}
                    </p>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-4 text-sm text-slate-500">
              Jadwal pembangunan rumah Anda belum ditetapkan tim proyek. Progres per tahapan
              akan muncul di sini begitu jadwal dibuat.
            </p>
          )}

          <div className="mt-5 border-t pt-4">
            <p className="mb-2 text-sm font-semibold">Pekerjaan kawasan (bukan rumah Anda)</p>
            <p className="mb-2 text-[11px] text-slate-500">
              Jalan, drainase, dan fasilitas umum yang dikerjakan untuk seluruh perumahan.
            </p>
            <div className="space-y-2">
              {(u.phases || []).map((ph, i) => (
                <div key={i} data-phase={ph.name} className="flex items-center gap-3">
                  <div className="w-40 shrink-0 text-sm text-slate-600">{ph.name}</div>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-emerald-500"
                      style={{ width: `${ph.progress || 0}%` }} />
                  </div>
                  <div className="w-10 text-right text-xs tabular-nums text-slate-500">
                    {ph.progress || 0}%
                  </div>
                </div>
              ))}
              {!u.phases?.length ? (
                <p className="text-sm text-slate-400">Pekerjaan kawasan belum tersedia.</p>
              ) : null}
            </div>
          </div>

          <div className="mt-5 border-t pt-4">
            <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
              <Camera className="h-4 w-4 text-indigo-600" />
              Foto lapangan terbaru ({(u.photos || []).length})
            </p>
            <div data-testid={PORTAL.progressPhotos}>
              <PhotoGallery photos={u.photos || []} portal columns={3}
                emptyText="Belum ada foto lapangan yang diunggah tim proyek." />
            </div>
            <p className="mt-2 text-[11px] text-slate-500">
              Foto bertanda “kavling ini” diambil pada unit Anda; “lapangan proyek” adalah
              dokumentasi umum area proyek.
            </p>
          </div>

          <div className="mt-5 border-t pt-4">
            <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
              <Wrench className="h-4 w-4 text-emerald-600" />
              Bukti perbaikan: sebelum → sesudah ({(u.repairs || []).length})
            </p>
            <p className="mb-2 text-[11px] text-slate-500">
              Geser pemisah pada foto untuk membandingkan kondisi sebelum dan sesudah dikerjakan.
            </p>
            <div data-testid={PORTAL.repairs}>
              <BeforeAfterCompare repairs={u.repairs || []} portal
                emptyText="Belum ada temuan perbaikan yang didokumentasikan pada unit Anda." />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
