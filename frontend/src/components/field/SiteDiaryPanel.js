import React, { useCallback, useEffect, useState } from "react";
import { Plus, CloudSun, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import PhotoGallery from "@/components/patterns/PhotoGallery";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AddDiaryDialog from "@/components/field/AddDiaryDialog";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, formatDateTimeWIB } from "@/utils/formatters";
import { toPhotoList } from "@/utils/photoSrc";
import api from "@/services/apiClient";
import { FIELD } from "@/constants/testIds";


export default function SiteDiaryPanel({ projectId }) {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("construction", "create");
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/field/diary", { params: { project_id: projectId } });
      setRows(r.data.data || []);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat buku harian."); }
    finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid={FIELD.diaryPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Catatan harian aktivitas lapangan: cuaca, tenaga kerja, pekerjaan, & kendala.</p>
        {canManage ? (
          <Button data-testid={FIELD.diaryAddBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Catatan
          </Button>
        ) : null}
      </div>
      {loading ? <LoadingCards count={3} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !rows?.length ? (
          <EmptyState icon={CloudSun} title="Belum ada catatan harian"
            description="Tambahkan buku harian lapangan pertama untuk proyek ini."
            actionLabel={canManage ? "Tambah Catatan" : undefined} onAction={() => setAddOpen(true)} />
        ) : (
          <div className="space-y-3">
            {rows.map((d) => (
              <div key={d.id} data-testid={FIELD.diaryRow} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-heading text-sm font-semibold">{formatDateWIB(d.log_date)}</p>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1"><CloudSun className="h-3.5 w-3.5" /> {d.weather || "-"}</span>
                    <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {d.workforce || 0} pekerja</span>
                  </div>
                </div>
                <p className="mt-2 text-sm">{d.work_description}</p>
                <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                  {d.materials ? <span>Material: {d.materials}</span> : null}
                  {d.equipment ? <span>Alat: {d.equipment}</span> : null}
                  {d.obstacles ? <span className="text-amber-700">Kendala: {d.obstacles}</span> : null}
                </div>
                <div className="mt-2">
                  <PhotoGallery columns={4} showMeta={false}
                    photos={toPhotoList(d, { label: d.work_description, date: d.log_date, scope: "proyek" })} />
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">{d.actor} · {formatDateTimeWIB(d.created_at)}</p>
              </div>
            ))}
          </div>
        )}
      <AddDiaryDialog projectId={projectId} open={addOpen} onOpenChange={setAddOpen} onDone={load} />
    </div>
  );
}
